"""Redis cache backend for mubu-mcp.

Install: pip install "mubu-mcp[redis]"
Env:     MUBU_REDIS_URL (default redis://localhost:6379/0)
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from mubu_mcp.cache.base import CacheBackend

_KEY_PREFIX = "mubu:"


class RedisCache(CacheBackend):
    """Redis-backed cache using a plain key–value layout."""

    def __init__(self, url: Optional[str] = None) -> None:
        try:
            import redis as _redis  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "Redis backend requires the 'redis' package. "
                'Install it with: pip install "mubu-mcp[redis]"'
            ) from exc

        self._url = url or os.getenv("MUBU_REDIS_URL", "redis://localhost:6379/0")
        self._client = _redis.Redis.from_url(
            self._url, decode_responses=True, socket_connect_timeout=5
        )

    def _k(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"

    def get(self, key: str) -> Optional[Any]:
        raw = self._client.get(self._k(key))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        if ttl is not None:
            self._client.setex(self._k(key), int(ttl), payload)
        else:
            self._client.set(self._k(key), payload)

    def delete(self, key: str) -> bool:
        return bool(self._client.delete(self._k(key)))

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(self._k(key)))

    def clear(self, prefix: str = "") -> int:
        pattern = f"{_KEY_PREFIX}{prefix}*" if prefix else f"{_KEY_PREFIX}*"
        keys = list(self._client.scan_iter(match=pattern, count=500))
        if keys:
            return self._client.delete(*keys)
        return 0
