"""Azure Cosmos DB cache backend for mubu-mcp.

Install: pip install "mubu-mcp[cosmos]"
Env:     MUBU_COSMOS_ENDPOINT   (required)
        MUBU_COSMOS_KEY        (required)
        MUBU_COSMOS_DB         (default mubu_cache)
        MUBU_COSMOS_CONTAINER  (default mubu_data)
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from mubu_mcp.cache.base import CacheBackend


class CosmosCache(CacheBackend):
    """Azure Cosmos DB (NoSQL) backed cache using a single container."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        key: Optional[str] = None,
        database: Optional[str] = None,
        container: Optional[str] = None,
    ) -> None:
        try:
            from azure.cosmos import CosmosClient, PartitionKey  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "CosmosDB backend requires the 'azure-cosmos' package. "
                'Install it with: pip install "mubu-mcp[cosmos]"'
            ) from exc

        self._endpoint = endpoint or os.getenv("MUBU_COSMOS_ENDPOINT", "")
        self._key = key or os.getenv("MUBU_COSMOS_KEY", "")
        self._db_name = database or os.getenv("MUBU_COSMOS_DB", "mubu_cache")
        self._container_name = container or os.getenv("MUBU_COSMOS_CONTAINER", "mubu_data")

        if not self._endpoint or not self._key:
            raise ValueError(
                "CosmosDB requires MUBU_COSMOS_ENDPOINT and MUBU_COSMOS_KEY."
            )

        client = CosmosClient(self._endpoint, self._key)
        db = client.create_database_if_not_exists(id=self._db_name)
        self._container = db.create_container_if_not_exists(
            id=self._container_name,
            partition_key=PartitionKey(path="/pk"),
            offer_throughput=400,
        )

    def _doc(self, key: str, value: Any, ttl: Optional[float] = None) -> dict:
        expires_at = (time.time() + ttl) if ttl is not None else None
        return {
            "id": key,
            "pk": key,
            "value": value,
            "expires_at": expires_at,
        }

    def _is_alive(self, doc: dict) -> bool:
        exp = doc.get("expires_at")
        if exp is None:
            return True
        return time.time() < exp

    def get(self, key: str) -> Optional[Any]:
        try:
            doc = self._container.read_item(item=key, partition_key=key)
        except Exception:
            return None
        if not self._is_alive(doc):
            self.delete(key)
            return None
        return doc.get("value")

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        doc = self._doc(key, value, ttl)
        self._container.upsert_item(doc)

    def delete(self, key: str) -> bool:
        try:
            self._container.delete_item(item=key, partition_key=key)
            return True
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        try:
            doc = self._container.read_item(item=key, partition_key=key)
        except Exception:
            return False
        if not self._is_alive(doc):
            self.delete(key)
            return False
        return True

    def clear(self, prefix: str = "") -> int:
        query = "SELECT c.id FROM c"
        items = list(self._container.query_items(
            query=query, partition_key=True, enable_cross_partition_query=True
        ))
        count = 0
        for item in items:
            doc_id = item.get("id", "")
            if not prefix or doc_id.startswith(prefix):
                try:
                    self._container.delete_item(item=doc_id, partition_key=doc_id)
                    count += 1
                except Exception:
                    pass
        return count
