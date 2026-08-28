"""Mubu MCP — API client with pluggable cache integration.

Ported from mubu-integration (liuboacean/mubu-integration) and adapted
to use the CacheBackend abstraction for token / user / document caching.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from mubu_mcp.cache.base import CacheBackend
from mubu_mcp.mubu_config import (
    BASE_URL,
    DEFAULT_HEADERS,
    ENDPOINTS,
    MAX_NETWORK_RETRIES,
    MAX_SEARCH_DEPTH,
    MAX_SEARCH_LIMIT,
    MAX_SEARCH_REQUESTS,
    NETWORK_BACKOFF,
    REQUEST_TIMEOUT,
    MubuError,
    logger,
)
from mubu_mcp.mubu_convert import (
    export_markdown,
    normalize_node,
    safe_filename,
)


class MubuClient:
    """Mubu API client backed by a pluggable cache."""

    def __init__(
        self,
        phone: Optional[str] = None,
        password: Optional[str] = None,
        cache: Optional[CacheBackend] = None,
        member_id: Optional[str] = None,
    ) -> None:
        self._load_env_file()

        self.phone = phone or os.getenv("MUBU_PHONE")
        self.password = password or os.getenv("MUBU_PASSWORD")

        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self.member_id: Optional[str] = None
        self.expires_at: float = 0.0

        self._cache = cache
        self._session = requests.Session()
        self._client_unique_id = str(uuid.uuid4())
        self._session_id = str(uuid.uuid4())

        # Restore cached token
        self._load_token()

        # member_id priority: env > cache > constructor arg
        if not self.member_id:
            self.member_id = member_id or os.getenv("MUBU_MEMBER_ID")

    # ------------------------------------------------------------------
    # Env file loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_env_file() -> None:
        env_path = os.path.expanduser("~/.workbuddy/.env.mubu")
        if not os.path.isfile(env_path):
            return
        try:
            for line in open(env_path, encoding="utf-8").read().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("\"'")
                if key in ("MUBU_PHONE", "MUBU_PASSWORD", "MUBU_MEMBER_ID") and not os.getenv(key):
                    os.environ[key] = value
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Token persistence (via cache or file fallback)
    # ------------------------------------------------------------------

    def _load_token(self) -> bool:
        # Try cache first
        if self._cache:
            data = self._cache.load_token()
            if data and time.time() < data.get("expires_at", 0):
                self.token = data["token"]
                self.user_id = data.get("user_id")
                self.username = data.get("username")
                self.member_id = data.get("member_id")
                self.expires_at = data["expires_at"]
                return True

        # File fallback
        token_file = os.path.expanduser("~/.mubu_token")
        if os.path.isfile(token_file):
            try:
                data = json.loads(open(token_file).read())
                if time.time() < data.get("expires_at", 0):
                    self.token = data.get("token")
                    self.user_id = data.get("user_id")
                    self.username = data.get("username")
                    self.member_id = data.get("member_id")
                    self.expires_at = data["expires_at"]
                    # Promote to cache
                    if self._cache:
                        self._cache.store_token(
                            self.token,  # type: ignore[arg-type]
                            self.user_id or "",  # type: ignore[arg-type]
                            self.username or "",  # type: ignore[arg-type]
                            self.member_id,
                        )
                    return True
            except Exception:
                pass
        return False

    def _save_token(self) -> None:
        self.expires_at = time.time() + 7200
        data = {
            "token": self.token,
            "user_id": self.user_id,
            "username": self.username,
            "member_id": self.member_id,
            "expires_at": self.expires_at,
        }
        if self._cache:
            self._cache.store_token(
                self.token or "",  # type: ignore[arg-type]
                self.user_id or "",  # type: ignore[arg-type]
                self.username or "",  # type: ignore[arg-type]
                self.member_id,
            )
        # Also write file for backward-compat
        token_file = os.path.expanduser("~/.mubu_token")
        try:
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
            tmp = token_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.rename(tmp, token_file)
            os.chmod(token_file, 0o600)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
        headers = DEFAULT_HEADERS.copy()
        if self.token:
            headers["Jwt-Token"] = self.token
        headers["data-unique-id"] = self._client_unique_id
        headers["x-session-id"] = f"{self._session_id}:{int(time.time())}"
        headers["x-reg-entrance"] = "https://mubu.com/app"
        headers["x-request-id"] = str(uuid.uuid4())
        return headers

    def ensure_valid_token(self) -> None:
        if not self.token or time.time() > self.expires_at - 360:
            self.login()

    def _is_auth_error(self, result: Dict[str, Any], response: requests.Response) -> bool:
        if response.status_code == 401:
            return True
        code = result.get("code")
        if code is not None and code != 0:
            msg = str(result.get("msg", "")).lower()
            for kw in ("登录", "未登录", "重新登录", "登录失效", "unauthorized"):
                if kw in msg:
                    return True
        return False

    def _http_request(self, method: str, url: str, headers: Dict[str, str], **kwargs: Any) -> requests.Response:
        last_err: Optional[Exception] = None
        for attempt in range(MAX_NETWORK_RETRIES + 1):
            try:
                response = self._session.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
            except requests.exceptions.RequestException as e:
                last_err = e
                if attempt < MAX_NETWORK_RETRIES:
                    time.sleep(NETWORK_BACKOFF[min(attempt, len(NETWORK_BACKOFF) - 1)])
                    continue
                raise MubuError(f"Network error after {MAX_NETWORK_RETRIES} retries: {e}")

            if response.status_code == 429:
                if attempt < MAX_NETWORK_RETRIES:
                    retry_after = response.headers.get("Retry-After")
                    wait = min(int(retry_after), 30) if retry_after and str(retry_after).isdigit() else NETWORK_BACKOFF[min(attempt, len(NETWORK_BACKOFF) - 1)]
                    time.sleep(wait)
                    continue
                raise MubuError("Rate limited (HTTP 429)", status_code=429)

            if response.status_code >= 500:
                if attempt < MAX_NETWORK_RETRIES:
                    time.sleep(NETWORK_BACKOFF[min(attempt, len(NETWORK_BACKOFF) - 1)])
                    continue
                raise MubuError(f"Server unavailable (HTTP {response.status_code})", status_code=response.status_code)

            return response

        raise MubuError(f"Request failed: {last_err}")

    def _request(self, method: str, endpoint: str, *, max_retries: int = 1, auth: bool = True, **kwargs: Any) -> Dict:
        if auth:
            self.ensure_valid_token()
        url = f"{BASE_URL}{endpoint}"
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        response = self._http_request(method, url, headers, **kwargs)

        try:
            result = response.json()
        except ValueError:
            raise MubuError(f"Non-JSON response (status={response.status_code})", status_code=response.status_code, body=response.text[:300])

        if self._is_auth_error(result, response):
            if max_retries > 0:
                self.login()
                return self._request(method, endpoint, max_retries=max_retries - 1, auth=auth, **kwargs)
            raise MubuError(f"Auth failed: {result.get('msg', 'unknown')}", status_code=response.status_code, body=result)

        if result.get("code") != 0:
            if response.status_code == 403:
                raise MubuError(f"Forbidden: {result.get('msg', 'unknown')}", status_code=403, body=result)
            raise MubuError(f"API error: {result.get('msg', 'unknown')}", status_code=response.status_code, body=result)

        return result.get("data", {})

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> Dict:
        if not self.phone or not self.password:
            raise MubuError("Set MUBU_PHONE and MUBU_PASSWORD env vars or pass them to the constructor.")

        data = self._request(*ENDPOINTS["login"], auth=False, max_retries=0, json={
            "phone": self.phone,
            "password": self.password,
            "callbackType": 0,
        })
        self.token = data["token"]
        self.user_id = data["id"]
        self.username = data["name"]
        if not self.member_id:
            self.member_id = data.get("memberId") or data.get("member_id")
        self._save_token()
        return {"token": self.token, "user_id": self.user_id, "username": self.username}

    def ensure_login(self) -> None:
        if not self.token:
            self.login()

    # ------------------------------------------------------------------
    # Document / folder operations
    # ------------------------------------------------------------------

    def get_list(self, folder_id: str = "0") -> Dict:
        return self._request(*ENDPOINTS["list"], json={"folderId": folder_id})

    def create_folder(self, name: str, parent_id: str = "0") -> str:
        data = self._request(*ENDPOINTS["create_folder"], json={"folderId": parent_id, "name": name})
        return data.get("folder", {}).get("id", "")

    def create_doc(self, name: str, folder_id: str = "0", content: str = "") -> str:
        data = self._request(*ENDPOINTS["create_doc"], json={"folderId": folder_id, "name": name, "content": content})
        doc_id = data.get("doc", {}).get("id", "")
        if self._cache and doc_id:
            self._cache.invalidate_doc(doc_id)
        return doc_id

    def get_doc(self, doc_id: str) -> Dict:
        # Check cache first
        if self._cache:
            cached = self._cache.load_doc(doc_id)
            if cached:
                return cached

        self.ensure_login()
        data = self._request(*ENDPOINTS["get_doc"], json={
            "docId": doc_id, "password": "", "isFromDocDir": True,
        })
        try:
            definition = json.loads(data["definition"])
        except (KeyError, TypeError, ValueError) as e:
            raise MubuError(f"Failed to parse doc definition (doc_id={doc_id}): {e}") from e

        result = {"name": data.get("name"), "nodes": definition.get("nodes", [])}

        # Cache the result
        if self._cache:
            self._cache.store_doc(doc_id, result)

        return result

    def build_update_event(self, doc_definition: Dict, doc_id: str) -> Dict:
        nodes = doc_definition.get("nodes", []) if isinstance(doc_definition, dict) else []
        normalized_nodes = [normalize_node(n) for n in nodes]
        root = {"id": doc_id, "children": normalized_nodes, "modified": int(time.time() * 1000)}
        return {"name": "update", "updated": [{"updated": root, "original": root}]}

    def save_doc(self, doc_id: str, events: Optional[List[Dict]] = None, version: Optional[int] = None, name: Optional[str] = None) -> None:
        if version is None or events is None:
            raw = self._request(*ENDPOINTS["get_doc"], json={"docId": doc_id, "password": "", "isFromDocDir": True})
            if version is None:
                version = raw.get("baseVersion")
            if events is None:
                definition = json.loads(raw["definition"])
                events = [self.build_update_event(definition, doc_id)]

        if not self.member_id:
            raise MubuError(
                "Saving requires MUBU_MEMBER_ID. Set it as an env var "
                "(find it in your browser's mubu.com network requests)."
            )

        payload = {
            "memberId": self.member_id,
            "type": "CHANGE",
            "version": version,
            "documentId": doc_id,
            "events": events,
        }
        headers = {"x-reg-entrance": f"https://mubu.com/app/edit/home/{doc_id}"}
        self._request(*ENDPOINTS["save_doc"], json=payload, headers=headers)

        if self._cache:
            self._cache.invalidate_doc(doc_id)

        if name:
            self.rename_doc(doc_id, name)

    def delete_folder(self, folder_id: str) -> None:
        self._request(*ENDPOINTS["delete_folder"], json={"id": folder_id})

    def delete_doc(self, doc_id: str) -> None:
        self._request(*ENDPOINTS["delete_doc"], json={"id": doc_id})
        if self._cache:
            self._cache.invalidate_doc(doc_id)

    def move(self, item_id: str, target_folder_id: str, item_type: str = "doc") -> None:
        self._request(*ENDPOINTS["move"], json={
            "dst": None,
            "src": [{"type": item_type, "id": item_id}],
            "folderId": target_folder_id,
        })

    def rename_doc(self, doc_id: str, new_name: str) -> None:
        self._request(*ENDPOINTS["rename_doc"], json={"documentId": doc_id, "name": new_name})
        if self._cache:
            self._cache.invalidate_doc(doc_id)

    def rename_folder(self, folder_id: str, new_name: str) -> None:
        self._request("POST", "/list/rename_folder", json={
            "id": folder_id, "name": new_name, "folderId": folder_id,
        })

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        keyword: str,
        root_folder_id: str = "0",
        max_depth: int = MAX_SEARCH_DEPTH,
        limit: int = MAX_SEARCH_LIMIT,
        max_requests: int = MAX_SEARCH_REQUESTS,
        include_content: bool = False,
    ) -> Dict[str, Any]:
        keyword_lower = keyword.lower()
        results: List[Dict[str, Any]] = []
        req_count = 0
        truncated = False
        visited: set = set()

        def walk(folder_id: str, path: str, depth: int) -> None:
            nonlocal req_count, truncated
            if folder_id in visited:
                return
            visited.add(folder_id)
            if truncated or depth > max_depth or req_count >= max_requests:
                if depth > max_depth or req_count >= max_requests:
                    truncated = True
                return
            try:
                data = self.get_list(folder_id)
            except MubuError as e:
                logger.warning("Folder traversal failed for %s: %s", folder_id, e)
                return
            req_count += 1
            if len(results) >= limit:
                truncated = True
                return

            folders = data.get("folders", []) or []
            docs = data.get("documents") or data.get("docs") or []

            for d in docs:
                doc_id = d.get("id")
                name = d.get("name") or ""
                if keyword_lower and keyword_lower in name.lower():
                    results.append({"id": doc_id, "name": name, "type": "doc", "path": path, "matched_in": "name"})
                    if len(results) >= limit:
                        truncated = True
                        return
                    continue
                if include_content and keyword_lower:
                    try:
                        doc = self.get_doc(doc_id)
                    except MubuError:
                        continue
                    if _keyword_in_nodes(doc.get("nodes", []), keyword_lower):
                        results.append({"id": doc_id, "name": name, "type": "doc", "path": path, "matched_in": "content"})
                        if len(results) >= limit:
                            truncated = True
                            return

            for f in folders:
                fid = f.get("id")
                fname = f.get("name") or ""
                if keyword_lower and fname.lower() and keyword_lower in fname.lower():
                    results.append({"id": fid, "name": fname, "type": "folder", "path": path})
                    if len(results) >= limit:
                        truncated = True
                        return
                child_path = f"{path}/{fname}" if path else fname
                walk(fid, child_path, depth + 1)

        walk(root_folder_id, "", 0)
        return {"results": results, "truncated": truncated, "limit": limit, "max_depth": max_depth}

    def export_tree(self, root_folder_id: str = "0", max_depth: int = MAX_SEARCH_DEPTH) -> Dict[str, int]:
        """Export a folder tree as in-memory nested Markdown. Returns {docs, errors}."""
        stats: Dict[str, int] = {"docs": 0, "errors": 0}

        def walk(folder_id: str, depth: int) -> Dict[str, Any]:
            if depth > max_depth:
                return {}
            try:
                data = self.get_list(folder_id)
            except MubuError:
                stats["errors"] += 1
                return {}

            result: Dict[str, Any] = {}
            folders = data.get("folders", []) or []
            docs = data.get("documents") or data.get("docs") or []

            for d in docs:
                doc_id = d.get("id")
                name = (d.get("name") or "untitled").strip()
                try:
                    doc = self.get_doc(doc_id)
                    md = export_markdown(doc)
                    result[f"{safe_filename(name)}.md"] = md
                    stats["docs"] += 1
                except MubuError:
                    stats["errors"] += 1

            for f in folders:
                fname = (f.get("name") or "untitled").strip()
                result[safe_filename(fname)] = walk(f.get("id", ""), depth + 1)

            return result

        tree = walk(root_folder_id, 0)
        return {"tree": tree, **stats}


def _keyword_in_nodes(nodes: Any, keyword_lower: str) -> bool:
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        text = (node.get("text") or "")
        note = (node.get("note") or "")
        if keyword_lower in (text + " " + note).lower():
            return True
        if _keyword_in_nodes(node.get("children", []), keyword_lower):
            return True
    return False
