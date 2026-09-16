"""Mubu MCP Server — exposes Mubu (幕布) outline operations via MCP tools.

Built on the MCP Python SDK v2 (2026-07-28 spec).
Uses a pluggable cache backend (SQLite built-in) for token and user info caching.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Optional

from mcp.server import MCPServer

from mubu_mcp.cache import get_cache_backend
from mubu_mcp.cache.base import CacheBackend
from mubu_mcp.mubu_client import MubuClient
from mubu_mcp.mubu_convert import (
    doc_to_freeplane,
    doc_to_opml,
    doc_to_markdown,
    export_markdown,
    markdown_to_doc,
    markdown_to_mubu_tree,
)
from mubu_mcp.mubu_config import MubuError, logger

# ---------------------------------------------------------------------------
# Initialise MCP server
# ---------------------------------------------------------------------------

mcp = MCPServer("mubu-mcp")

# ---------------------------------------------------------------------------
# Lazy-initialised shared objects
# ---------------------------------------------------------------------------

_cache: Optional[CacheBackend] = None
_client: Optional[MubuClient] = None


def _get_cache() -> CacheBackend:
    global _cache
    if _cache is None:
        _cache = get_cache_backend()
    return _cache


def _get_client() -> MubuClient:
    global _client
    if _client is None:
        _client = MubuClient(cache=_get_cache())
    return _client


# ---------------------------------------------------------------------------
# Helpers for folder-path resolution and auto naming
# ---------------------------------------------------------------------------


def _auto_name() -> str:
    """Auto-generate a document name: mbmcp_YYYYMMDD_HHMMSS (local time)."""
    return "mbmcp_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_folder(client: MubuClient, folder_id: str, folder_path: str) -> str:
    """Resolve the target folder: ``folder_path`` takes priority (auto-created
    if missing), otherwise fall back to ``folder_id`` ("0" = root)."""
    if folder_path and folder_path.strip():
        return client.ensure_folder_path(folder_path)
    return folder_id or "0"


def _plain_text(node_html: str) -> str:
    """Strip <span>…</span> (or any tags) from a node's text field."""
    import re as _re
    return _re.sub(r"<[^>]+>", "", node_html or "").strip()


def _write_doc_content(client: MubuClient, doc_id: str, markdown: str, name: str = "") -> tuple[str, bool]:
    """Write parsed Markdown content into a Mubu document.

    Strategy (verified against the live server):
    - Empty document (no nodes)          → create root node with full subtree in place.
    - Document with root only            → update root text + create children under it.
    - Document with existing children    → delete + recreate (same name & folder);
                                            returns the new doc id (recreated=True).
    Returns ``(final_doc_id, recreated)``.
    """
    root_node = markdown_to_mubu_tree(markdown)
    doc = client.get_doc(doc_id)
    nodes = doc.get("nodes") or []

    if not nodes:
        client.save_doc(doc_id, events=[client.build_create_root_event(root_node)])
        return doc_id, False

    old_root = nodes[0]
    children = old_root.get("children") or []
    if not children:
        events = [client.build_update_root_event(old_root, _plain_text(root_node.get("text")))]
        events.extend(client.build_create_children_events(old_root.get("id", ""), root_node.get("children") or []))
        client.save_doc(doc_id, events=events)
        return doc_id, False

    # Existing content cannot be replaced in place (no delete event); recreate.
    meta = client.get_doc_meta(doc_id)
    new_name = name.strip() if name and name.strip() else (meta.get("name") or _auto_name())
    client.delete_doc(doc_id)
    new_id = client.create_doc(new_name, meta.get("folder_id") or "0")
    client.save_doc(new_id, events=[client.build_create_root_event(root_node)])
    return new_id, True


# ===================================================================
# TOOLS
# ===================================================================

# --- Auth ---------------------------------------------------------------


@mcp.tool()
def mubu_login() -> str:
    """Login to Mubu (幕布).

    Reads credentials from MUBU_PHONE / MUBU_PASSWORD env vars
    (or ~/.workbuddy/.env.mubu). Returns the authenticated username.
    """
    client = _get_client()
    info = client.login()
    return f"Logged in as {info['username']} (user_id={info['user_id']})"


@mcp.tool()
def mubu_whoami() -> str:
    """Return current Mubu auth status (username, user_id, cache backend)."""
    client = _get_client()
    cache = _get_cache()
    token_info = cache.load_token()
    if not client.token and not token_info:
        return "Not logged in. Call mubu_login first."
    username = client.username or (token_info or {}).get("username", "unknown")
    user_id = client.user_id or (token_info or {}).get("user_id", "unknown")
    backend_name = type(cache).__name__
    return f"User: {username} (id={user_id}), cache_backend={backend_name}"


# --- List / browse -------------------------------------------------------


@mcp.tool()
def mubu_list(folder_id: str = "0") -> str:
    """List documents and sub-folders in a Mubu folder.

    Args:
        folder_id: Folder ID to list. Use "0" for root.
    """
    client = _get_client()
    data = client.get_list(folder_id)
    folders = data.get("folders", []) or []
    docs = data.get("documents") or data.get("docs") or []

    lines: list[str] = []
    if folders:
        lines.append("📁 Folders:")
        for f in folders:
            lines.append(f"  [{f.get('id', '')}] {f.get('name', 'untitled')}")
    if docs:
        lines.append("📄 Documents:")
        for d in docs:
            lines.append(f"  [{d.get('id', '')}] {d.get('name', 'untitled')}")
    if not folders and not docs:
        lines.append("(empty)")
    return "\n".join(lines)


# --- Create ------------------------------------------------------------


@mcp.tool()
def mubu_create_folder(name: str, parent_id: str = "0") -> str:
    """Create a new folder in Mubu.

    Args:
        name: Folder name.
        parent_id: Parent folder ID. Use "0" for root.
    """
    client = _get_client()
    fid = client.create_folder(name, parent_id)
    return f"Folder created: [{fid}] {name}"


@mcp.tool()
def mubu_create_doc(name: str, folder_id: str = "0") -> str:
    """Create a new empty document in Mubu.

    Args:
        name: Document title.
        folder_id: Parent folder ID. Use "0" for root.
    """
    client = _get_client()
    doc_id = client.create_doc(name, folder_id)
    return f"Document created: [{doc_id}] {name}"


@mcp.tool()
def mubu_create_doc_from_markdown(markdown: str, name: str = "", folder_id: str = "0", folder_path: str = "") -> str:
    """Create a Mubu document from Markdown content.

    The Markdown is parsed into a Mubu outline structure. Supports headings,
    bullet lists, checkboxes ([x] / [ ]), and block quotes (> note).

    Output style (default, i-have-adhd): organize the Markdown as a 2-5 level
    outline — lead with an actionable first line, one-sentence conclusion per
    section, numbered steps, concrete time estimates, visible evidence, error
    codes stated plainly, lists capped at 5 per group, no pleasantries.
    See skill references/i-have-adhd.md for the full rules; follow the user's
    explicit style request when one is given.

    Args:
        name: Document title. If empty, auto-generated as "mbmcp_<timestamp>"
              (e.g. mbmcp_20260916_121530).
        markdown: Markdown content to import.
        folder_id: Parent folder ID. Use "0" for root (ignored when folder_path is set).
        folder_path: Folder path like "工作/项目A/子目录"; existing folders are reused,
                     missing ones are created automatically.
    """
    client = _get_client()
    folder_id = _resolve_folder(client, folder_id, folder_path)
    if not name or not name.strip():
        name = _auto_name()
    root_node = markdown_to_mubu_tree(markdown)
    doc_id = client.create_doc(name, folder_id)
    client.save_doc(doc_id, events=[client.build_create_root_event(root_node)])
    target = folder_path.strip() if folder_path and folder_path.strip() else f"[{folder_id}]"
    return f"Document created from Markdown: [{doc_id}] {name} (folder: {target})"


# --- Get / read ---------------------------------------------------------


@mcp.tool()
def mubu_get_doc(doc_id: str, as_markdown: bool = True) -> str:
    """Get a Mubu document's content.

    Args:
        doc_id: The document ID.
        as_markdown: If True, export as round-trip Markdown. If False, return raw JSON.
    """
    client = _get_client()
    doc = client.get_doc(doc_id)
    if as_markdown:
        return export_markdown(doc)
    return json.dumps(doc, ensure_ascii=False, indent=2)


@mcp.tool()
def mubu_get_doc_raw(doc_id: str) -> str:
    """Get a Mubu document's raw JSON structure (nodes, metadata)."""
    client = _get_client()
    doc = client.get_doc(doc_id)
    return json.dumps(doc, ensure_ascii=False, indent=2)


# --- Save / update ------------------------------------------------------


@mcp.tool()
def mubu_save_doc_markdown(doc_id: str, markdown: str, folder_path: str = "", name: str = "") -> str:
    """Overwrite a Mubu document with new Markdown content.

    The Markdown is parsed into a Mubu outline structure and written
    back to the document (round-trip safe).

    Output style (default, i-have-adhd): same rules as
    mubu_create_doc_from_markdown — 2-5 level outline, actionable lead,
    one-sentence conclusions, numbered steps, concrete estimates, visible
    evidence, plain error codes, lists capped at 5 per group, no pleasantries.
    Follow the user's explicit style request when one is given.

    Args:
        doc_id: The document ID to update.
        markdown: New Markdown content.
        folder_path: Optional folder path like "工作/项目A/子目录"; existing folders
                     are reused, missing ones are created automatically, and the
                     document is moved there if it is not already inside.
        name: Optional new document name (applied after save).
    """
    client = _get_client()
    if folder_path and folder_path.strip():
        target = client.ensure_folder_path(folder_path)
        if not client.doc_exists_in_folder(target, doc_id):
            client.move(doc_id, target, "doc")
    final_id, recreated = _write_doc_content(client, doc_id, markdown, name=name)
    msg = f"Document [{doc_id}] updated from Markdown."
    if recreated:
        msg = (
            f"Document [{doc_id}] already had content that cannot be replaced in place; "
            f"recreated it as [{final_id}] (same folder). Use the new id for later saves."
        )
    if name and name.strip():
        if not recreated:
            client.rename_doc(final_id, name.strip())
        msg += f" Renamed to '{name.strip()}'."
    return msg


@mcp.tool()
def mubu_upsert_doc_markdown(markdown: str, name: str = "", folder_path: str = "", folder_id: str = "0") -> str:
    """Save Markdown as a Mubu document — create it if missing, update it if the
    target already exists.

    The target is resolved as ``folder_path`` (existing folders are reused,
    missing ones are created automatically) + ``name`` (auto-generated as
    "mbmcp_<timestamp>" when empty). If a document with the same name already
    exists in the target folder, its content is overwritten instead of creating
    a duplicate.

    Output style (default, i-have-adhd): same rules as
    mubu_create_doc_from_markdown — 2-5 level outline, actionable lead,
    one-sentence conclusions, numbered steps, concrete estimates, visible
    evidence, plain error codes, lists capped at 5 per group, no pleasantries.
    Follow the user's explicit style request when one is given.

    Args:
        markdown: Markdown content to import.
        name: Document title. If empty, auto-generated as "mbmcp_<timestamp>".
        folder_path: Folder path like "工作/项目A/子目录".
        folder_id: Parent folder ID. Use "0" for root (ignored when folder_path is set).
    """
    client = _get_client()
    folder_id = _resolve_folder(client, folder_id, folder_path)
    if not name or not name.strip():
        name = _auto_name()
    target = folder_path.strip() if folder_path and folder_path.strip() else f"[{folder_id}]"
    existing = client.find_doc_in_folder(folder_id, name)
    if existing:
        final_id, recreated = _write_doc_content(client, existing, markdown, name=name)
        if recreated:
            return f"Document recreated: [{final_id}] {name} (folder: {target}); previous id [{existing}] was replaced."
        return f"Document updated: [{final_id}] {name} (folder: {target})"
    root_node = markdown_to_mubu_tree(markdown)
    doc_id = client.create_doc(name, folder_id)
    client.save_doc(doc_id, events=[client.build_create_root_event(root_node)])
    return f"Document created: [{doc_id}] {name} (folder: {target})"


@mcp.tool()
def mubu_move(item_id: str, target_folder_id: str, item_type: str = "doc") -> str:
    """Move a document or folder to another folder.

    Args:
        item_id: ID of the item to move.
        target_folder_id: Destination folder ID. Use "0" for root.
        item_type: "doc" or "folder".
    """
    client = _get_client()
    client.move(item_id, target_folder_id, item_type)
    return f"Moved [{item_id}] ({item_type}) to folder [{target_folder_id}]."


@mcp.tool()
def mubu_rename(item_id: str, new_name: str, item_type: str = "doc") -> str:
    """Rename a document or folder.

    Args:
        item_id: ID of the item to rename.
        new_name: New name.
        item_type: "doc" or "folder".
    """
    client = _get_client()
    if item_type == "doc":
        client.rename_doc(item_id, new_name)
    else:
        client.rename_folder(item_id, new_name)
    return f"Renamed [{item_id}] to '{new_name}'."


@mcp.tool()
def mubu_delete(item_id: str, item_type: str = "doc") -> str:
    """Delete a document or folder (⚠️ irreversible on the server).

    Args:
        item_id: ID to delete.
        item_type: "doc" or "folder".
    """
    client = _get_client()
    if item_type == "doc":
        client.delete_doc(item_id)
    else:
        client.delete_folder(item_id)
    return f"Deleted [{item_id}] ({item_type})."


# --- Search -------------------------------------------------------------


@mcp.tool()
def mubu_search(keyword: str, include_content: bool = False, limit: int = 20) -> str:
    """Search Mubu documents and folders by name (case-insensitive).

    Args:
        keyword: Search keyword.
        include_content: Also search inside document bodies (slower, extra API calls).
        limit: Maximum results to return.
    """
    client = _get_client()
    result = client.search(keyword, limit=limit, include_content=include_content)
    items = result.get("results", [])
    truncated = result.get("truncated", False)

    if not items:
        return f"No results for '{keyword}'."

    lines: list[str] = []
    for item in items:
        matched = item.get("matched_in", "name")
        path = item.get("path", "")
        suffix = f" ({path})" if path else ""
        lines.append(f"  [{item['id']}] {item['name']} [{item['type']}]{suffix} (matched: {matched})")
    header = f"Search results for '{keyword}' ({len(items)} items"
    if truncated:
        header += ", truncated"
    header += "):"
    return header + "\n" + "\n".join(lines)


# --- Export (OPML / FreeMind) -------------------------------------------


@mcp.tool()
def mubu_export_opml(doc_id: str) -> str:
    """Export a Mubu document as OPML 2.0 XML.

    Compatible with XMind, OmniOutliner, and other outline tools.

    Args:
        doc_id: The document ID.
    """
    client = _get_client()
    doc = client.get_doc(doc_id)
    return doc_to_opml(doc)


@mcp.tool()
def mubu_export_freeplane(doc_id: str) -> str:
    """Export a Mubu document as FreeMind XML.

    Compatible with FreeMind, Freeplane, and XMind.

    Args:
        doc_id: The document ID.
    """
    client = _get_client()
    doc = client.get_doc(doc_id)
    return doc_to_freeplane(doc)


@mcp.tool()
def mubu_export_markdown(doc_id: str) -> str:
    """Export a Mubu document as round-trip Markdown.

    Supports headings, bullet lists, checkboxes, and notes.

    Args:
        doc_id: The document ID.
    """
    client = _get_client()
    doc = client.get_doc(doc_id)
    return export_markdown(doc)


@mcp.tool()
def mubu_import_markdown(markdown: str) -> str:
    """Parse Markdown into a Mubu document JSON structure (dry-run, no upload).

    Useful for previewing how Markdown will be converted before creating a doc.

    Args:
        markdown: Markdown content to parse.
    """
    doc = markdown_to_doc(markdown)
    return json.dumps(doc, ensure_ascii=False, indent=2)


@mcp.tool()
def mubu_export_tree(folder_id: str = "0") -> str:
    """Recursively export a folder tree as nested Markdown.

    Returns a JSON structure with all documents and sub-folders.

    Args:
        folder_id: Root folder ID. Use "0" for root.
    """
    client = _get_client()
    result = client.export_tree(folder_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


# --- Cache management ---------------------------------------------------


@mcp.tool()
def mubu_cache_info() -> str:
    """Show information about the current cache backend and stored keys."""
    cache = _get_cache()
    backend_name = type(cache).__name__
    has_token = cache.exists("auth:token")
    return (
        f"Cache backend: {backend_name}\n"
        f"Token cached: {'yes' if has_token else 'no'}\n"
    )


@mcp.tool()
def mubu_cache_clear(prefix: str = "") -> str:
    """Clear cached data. Optionally clear only keys with a given prefix.

    Args:
        prefix: Key prefix to clear (empty = clear everything).
    """
    cache = _get_cache()
    count = cache.clear(prefix)
    return f"Cleared {count} cache entries" + (f" with prefix '{prefix}'" if prefix else "") + "."


# ===================================================================
# RESOURCES
# ===================================================================


@mcp.resource("mubu://status")
def resource_mubu_status() -> str:
    """Current Mubu authentication and cache status."""
    client = _get_client()
    cache = _get_cache()
    token_info = cache.load_token()
    if client.token or token_info:
        username = client.username or (token_info or {}).get("username", "unknown")
        backend = type(cache).__name__
        return f"Authenticated as {username} | Cache: {backend}"
    return "Not authenticated. Use mubu_login tool."


@mcp.resource("mubu://doc/{doc_id}")
def resource_mubu_doc(doc_id: str) -> str:
    """Fetch a Mubu document by ID as Markdown."""
    client = _get_client()
    try:
        doc = client.get_doc(doc_id)
        return export_markdown(doc)
    except MubuError as e:
        return f"Error fetching document {doc_id}: {e}"


# ===================================================================
# PROMPTS
# ===================================================================


@mcp.prompt()
def mubu_setup_guide() -> str:
    """Step-by-step guide to configure Mubu MCP with credentials and cache."""
    return """## Mubu MCP Setup Guide

### 1. Set credentials (env vars or ~/.workbuddy/.env.mubu)

```bash
export MUBU_PHONE="your-phone-number"
export MUBU_PASSWORD="your-password"
# Optional: for save operations
export MUBU_MEMBER_ID="your-member-id"
```

### 2. Cache backend (default: SQLite, zero-config)

The server uses SQLite by default at `~/.mubu-mcp/cache.db`.
To use Redis, MongoDB, or CosmosDB, set:

```bash
# Redis
export MUBU_CACHE_BACKEND=redis
export MUBU_REDIS_URL=redis://localhost:6379/0

# MongoDB
export MUBU_CACHE_BACKEND=mongo
export MUBU_MONGO_URI=mongodb://localhost:27017
export MUBU_MONGO_DB=mubu_cache

# Cosmos DB
export MUBU_CACHE_BACKEND=cosmos
export MUBU_COSMOS_ENDPOINT=https://your-account.documents.azure.com
export MUBU_COSMOS_KEY=your-key
```

### 3. Start the MCP server

```bash
mubu-mcp                    # stdio transport (default)
mubu-mcp --transport http   # Streamable HTTP
```

### 4. Use the tools

Ask the AI to:
- "List my Mubu root folder"
- "Search for 'project plan' in Mubu"
- "Export document abc123 as Markdown"
- "Create a Mubu doc from this Markdown content"
"""


@mcp.prompt()
def mubu_work_with_doc(doc_id: str) -> str:
    """Load a Mubu document and present it for editing."""
    client = _get_client()
    try:
        doc = client.get_doc(doc_id)
        md = export_markdown(doc)
        return f"""Here is the Mubu document [{doc_id}] as Markdown:

{md}

You can now edit this content. When ready, call mubu_save_doc_markdown
with doc_id="{doc_id}" and the updated Markdown."""
    except MubuError as e:
        return f"Failed to load document {doc_id}: {e}"


@mcp.prompt()
def mubu_sync_markdown(markdown: str, folder_id: str = "0") -> str:
    """Import a Markdown outline into Mubu as a new document."""
    return f"""The following Markdown will be imported into Mubu folder [{folder_id}]:

{markdown}

Call mubu_create_doc_from_markdown with appropriate name and this content to create the document."""
