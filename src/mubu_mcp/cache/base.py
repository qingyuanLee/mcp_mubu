"""Abstract cache backend interface for mubu-mcp.

All cache backends implement this ABC so the MCP server and mubu client
can swap storage without touching business logic.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheBackend(ABC):
    """Base class every cache backend must implement.

    Keys are plain strings (e.g. ``"token"``, ``"user:<id>"``,
    ``"doc:<doc_id>"``, ``"list:<folder_id>"``).
    Values are arbitrary JSON-serialisable dicts/strings.
    Every entry may carry an optional TTL (seconds); ``None`` = no expiry.
    """

    # ------------------------------------------------------------------
    # Key–value CRUD
    # ------------------------------------------------------------------

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Return the cached value for *key*, or ``None`` if missing / expired."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store *value* under *key*.  *ttl* is seconds; ``None`` = no expiry."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove *key*. Return ``True`` if it existed."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists and has not expired."""

    @abstractmethod
    def clear(self, prefix: str = "") -> int:
        """Delete all keys starting with *prefix* (empty = everything).

        Return the number of keys removed.
        """

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_or_set(
        self, key: str, factory: Any, ttl: Optional[float] = None
    ) -> Any:
        """Return cached value or compute via *factory*, cache, and return."""
        val = self.get(key)
        if val is not None:
            return val
        val = factory() if callable(factory) else factory
        self.set(key, val, ttl=ttl)
        return val

    def store_token(
        self,
        token: str,
        user_id: str,
        username: str,
        member_id: Optional[str] = None,
        expires_in: float = 7200,
    ) -> None:
        """Persist an auth token with metadata."""
        self.set(
            "auth:token",
            {
                "token": token,
                "user_id": user_id,
                "username": username,
                "member_id": member_id,
                "expires_at": time.time() + expires_in,
            },
            ttl=expires_in,
        )

    def load_token(self) -> Optional[dict]:
        """Load cached auth token. Returns ``None`` if missing / expired."""
        return self.get("auth:token")  # type: ignore[return-value]

    def store_user_info(self, user_id: str, info: dict) -> None:
        """Cache user profile information."""
        self.set(f"user:{user_id}", info, ttl=86400)  # 24 h

    def load_user_info(self, user_id: str) -> Optional[dict]:
        """Load cached user profile."""
        return self.get(f"user:{user_id}")  # type: ignore[return-value]

    def store_doc(self, doc_id: str, doc: dict) -> None:
        """Cache a document snapshot (short-lived, to avoid repeated fetches)."""
        self.set(f"doc:{doc_id}", doc, ttl=300)  # 5 min

    def load_doc(self, doc_id: str) -> Optional[dict]:
        """Load a cached document snapshot."""
        return self.get(f"doc:{doc_id}")  # type: ignore[return-value]

    def invalidate_doc(self, doc_id: str) -> None:
        """Remove a cached document."""
        self.delete(f"doc:{doc_id}")
