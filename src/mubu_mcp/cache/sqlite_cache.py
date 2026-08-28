"""Built-in SQLite cache backend for mubu-mcp.

Zero external dependencies — uses Python's stdlib ``sqlite3``.
Database file lives at ``~/.mubu-mcp/cache.db`` by default.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from mubu_mcp.cache.base import CacheBackend

_DEFAULT_DB_DIR = Path.home() / ".mubu-mcp"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "cache.db"


class SqliteCache(CacheBackend):
    """SQLite-backed cache — thread-safe via per-thread connections."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection (per-thread)
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                expires_at REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON kv (expires_at)"
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_alive(self, row: sqlite3.Row) -> bool:
        exp = row["expires_at"]
        if exp is None:
            return True
        return time.time() < exp

    # ------------------------------------------------------------------
    # CacheBackend interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        conn = self._conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv WHERE key = ?", (key,)
        ).fetchone()
        if row is None or not self._is_alive(row):
            if row is not None:
                conn.execute("DELETE FROM kv WHERE key = ?", (key,))
                conn.commit()
            return None
        return json.loads(row["value"])

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expires_at = (time.time() + ttl) if ttl is not None else None
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO kv (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False, default=str), expires_at),
        )
        conn.commit()

    def delete(self, key: str) -> bool:
        conn = self._conn()
        cur = conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        conn.commit()
        return cur.rowcount > 0

    def exists(self, key: str) -> bool:
        conn = self._conn()
        row = conn.execute(
            "SELECT expires_at FROM kv WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return False
        if not self._is_alive(row):
            conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            conn.commit()
            return False
        return True

    def clear(self, prefix: str = "") -> int:
        conn = self._conn()
        if prefix:
            cur = conn.execute(
                "DELETE FROM kv WHERE key LIKE ?", (f"{prefix}%",)
            )
        else:
            cur = conn.execute("DELETE FROM kv")
        conn.commit()
        return cur.rowcount

    def vacuum(self) -> None:
        """Compact the database file (optional maintenance)."""
        conn = self._conn()
        conn.execute("VACUUM")
