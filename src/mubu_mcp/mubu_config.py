"""Mubu MCP — configuration, constants, and error types.

Ported from mubu-integration (liuboacean/mubu-integration) and adapted
for the MCP server context.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Dict, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("mubu_mcp")
logger.propagate = False
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# API base URL (domain-allowlisted)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api2.mubu.com/v3/api"
ALLOWED_BASE_HOSTS = ("api2.mubu.com", "api.mubu.com", "mubu.com")


def _resolve_base_url() -> str:
    env_url = os.getenv("MUBU_BASE_URL")
    if not env_url:
        return DEFAULT_BASE_URL
    try:
        host = urlparse(env_url).hostname or ""
    except Exception:
        host = ""
    if host in ALLOWED_BASE_HOSTS:
        return env_url.rstrip("/")
    logger.warning(
        "MUBU_BASE_URL host '%s' not in allowlist — using default %s",
        host, DEFAULT_BASE_URL,
    )
    return DEFAULT_BASE_URL


BASE_URL: str = _resolve_base_url()

# ---------------------------------------------------------------------------
# HTTP defaults
# ---------------------------------------------------------------------------

DEFAULT_HEADERS: Dict[str, str] = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://mubu.com",
    "Referer": "https://mubu.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT = 15
MAX_NETWORK_RETRIES = 2
NETWORK_BACKOFF = (1, 2)

# ---------------------------------------------------------------------------
# API endpoints: (HTTP method, path)
# ---------------------------------------------------------------------------

ENDPOINTS: Dict[str, Tuple[str, str]] = {
    "login":           ("POST", "/user/phone_login"),
    "list":            ("POST", "/list/get"),
    "create_folder":   ("POST", "/list/create_folder"),
    "create_doc":      ("POST", "/list/create_doc"),
    "get_doc":         ("POST", "/document/edit/get"),
    "save_doc":        ("POST", "/colla/events"),
    "rename_doc":      ("POST", "/list/rename_doc"),
    "delete_folder":   ("POST", "/list/delete_folder"),
    "delete_doc":      ("POST", "/list/delete_doc"),
    "move":            ("POST", "/list/custom/drag"),
}

# ---------------------------------------------------------------------------
# Search limits
# ---------------------------------------------------------------------------

MAX_SEARCH_DEPTH = 3
MAX_SEARCH_LIMIT = 50
MAX_SEARCH_REQUESTS = 200

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MubuError(Exception):
    """Base error for Mubu API operations."""

    def __init__(self, msg: str, status_code: int | None = None, body: object = None) -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status_code
        self.body = str(body)[:300] if body else None
