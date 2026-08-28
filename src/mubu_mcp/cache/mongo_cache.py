"""MongoDB cache backend for mubu-mcp.

Install: pip install "mubu-mcp[mongo]"
Env:     MUBU_MONGO_URI  (default mongodb://localhost:27017)
        MUBU_MONGO_DB    (default mubu_cache)
        MUBU_MONGO_COLLECTION (default mubu_data)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from mubu_mcp.cache.base import CacheBackend


class MongoCache(CacheBackend):
    """MongoDB-backed cache using a single collection with TTL index."""

    def __init__(
        self,
        uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        try:
            from pymongo import MongoClient  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "MongoDB backend requires the 'pymongo' package. "
                'Install it with: pip install "mubu-mcp[mongo]"'
            ) from exc

        self._uri = uri or os.getenv("MUBU_MONGO_URI", "mongodb://localhost:27017")
        self._db_name = db_name or os.getenv("MUBU_MONGO_DB", "mubu_cache")
        self._coll_name = collection_name or os.getenv(
            "MUBU_MONGO_COLLECTION", "mubu_data"
        )

        client = MongoClient(self._uri, serverSelectionTimeoutMS=5000)
        db = client[self._db_name]
        self._coll = db[self._coll_name]
        # Ensure TTL index on expires_at (0 = no expiry, MongoDB ignores it)
        self._coll.create_index("expires_at", expireAfterSeconds=0, background=True)

    def get(self, key: str) -> Optional[Any]:
        doc = self._coll.find_one({"_id": key})
        if doc is None:
            return None
        if doc.get("expires_at") and time.time() > doc["expires_at"]:
            self._coll.delete_one({"_id": key})
            return None
        return doc.get("value")

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expires_at = (time.time() + ttl) if ttl is not None else None
        self._coll.update_one(
            {"_id": key},
            {"$set": {"value": value, "expires_at": expires_at}},
            upsert=True,
        )

    def delete(self, key: str) -> bool:
        result = self._coll.delete_one({"_id": key})
        return result.deleted_count > 0

    def exists(self, key: str) -> bool:
        doc = self._coll.find_one(
            {"_id": key}, projection={"expires_at": 1}
        )
        if doc is None:
            return False
        if doc.get("expires_at") and time.time() > doc["expires_at"]:
            self._coll.delete_one({"_id": key})
            return False
        return True

    def clear(self, prefix: str = "") -> int:
        if prefix:
            result = self._coll.delete_many({"_id": {"$regex": f"^{prefix}"}})
        else:
            result = self._coll.delete_many({})
        return result.deleted_count
