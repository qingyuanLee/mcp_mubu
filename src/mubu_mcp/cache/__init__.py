"""Pluggable cache backends for mubu-mcp.

Built-in: SQLite (zero-config, local file).
Optional: Redis, MongoDB, CosmosDB — install via extras:
    pip install "mubu-mcp[redis]"
    pip install "mubu-mcp[mongo]"
    pip install "mubu-mcp[cosmos]"
    pip install "mubu-mcp[all]"
"""

from __future__ import annotations

import os
from typing import Optional

from mubu_mcp.cache.base import CacheBackend  # noqa: F401


def get_cache_backend(
    backend: Optional[str] = None,
    *,
    db_path: Optional[str] = None,
    redis_url: Optional[str] = None,
    mongo_uri: Optional[str] = None,
    mongo_db: Optional[str] = None,
    mongo_collection: Optional[str] = None,
    cosmos_endpoint: Optional[str] = None,
    cosmos_key: Optional[str] = None,
    cosmos_database: Optional[str] = None,
    cosmos_container: Optional[str] = None,
) -> CacheBackend:
    """Create a cache backend instance.

    Args:
        backend: Backend name — "sqlite" (default), "redis", "mongo", "cosmos".
            Falls back to env var ``MUBU_CACHE_BACKEND`` if not provided.
        db_path: SQLite database file path. Default ``~/.mubu-mcp/cache.db``.
        redis_url: Redis connection URL. Default env ``MUBU_REDIS_URL``.
        mongo_uri: MongoDB connection URI. Default env ``MUBU_MONGO_URI``.
        mongo_db: MongoDB database name. Default env ``MUBU_MONGO_DB`` / ``mubu_cache``.
        mongo_collection: MongoDB collection name. Default env ``MUBU_MONGO_COLLECTION`` / ``mubu_data``.
        cosmos_endpoint: CosmosDB endpoint URL. Default env ``MUBU_COSMOS_ENDPOINT``.
        cosmos_key: CosmosDB primary key. Default env ``MUBU_COSMOS_KEY``.
        cosmos_database: CosmosDB database name. Default env ``MUBU_COSMOS_DB`` / ``mubu_cache``.
        cosmos_container: CosmosDB container name. Default env ``MUBU_COSMOS_CONTAINER`` / ``mubu_data``.

    Returns:
        A CacheBackend instance.
    """
    backend = (backend or os.getenv("MUBU_CACHE_BACKEND", "")).lower().strip() or "sqlite"

    if backend == "sqlite":
        from mubu_mcp.cache.sqlite_cache import SqliteCache
        return SqliteCache(db_path=db_path)

    if backend == "redis":
        from mubu_mcp.cache.redis_cache import RedisCache
        return RedisCache(url=redis_url)

    if backend == "mongo":
        from mubu_mcp.cache.mongo_cache import MongoCache
        return MongoCache(
            uri=mongo_uri,
            db_name=mongo_db,
            collection_name=mongo_collection,
        )

    if backend == "cosmos":
        from mubu_mcp.cache.cosmos_cache import CosmosCache
        return CosmosCache(
            endpoint=cosmos_endpoint,
            key=cosmos_key,
            database=cosmos_database,
            container=cosmos_container,
        )

    raise ValueError(
        f"Unknown cache backend '{backend}'. "
        "Supported: sqlite, redis, mongo, cosmos."
    )
