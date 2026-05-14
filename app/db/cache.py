"""
Redis client wrapper with async support.
Provides typed helpers for common caching patterns.
"""
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Singleton client ──────────────────────────────────────────────────────────
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("redis_connection_closed")


# ── Typed helpers ─────────────────────────────────────────────────────────────
class Cache:
    """High-level caching helpers used by services."""

    def __init__(self, prefix: str = "", ttl: int = settings.redis_ttl_seconds):
        self.prefix = prefix
        self.default_ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}" if self.prefix else key

    async def get(self, key: str) -> Any | None:
        client = await get_redis()
        raw = await client.get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        client = await get_redis()
        serialized = json.dumps(value) if not isinstance(value, str) else value
        await client.setex(self._key(key), ttl or self.default_ttl, serialized)

    async def delete(self, key: str) -> None:
        client = await get_redis()
        await client.delete(self._key(key))

    async def exists(self, key: str) -> bool:
        client = await get_redis()
        return bool(await client.exists(self._key(key)))

    async def increment(self, key: str, ttl: int | None = None) -> int:
        client = await get_redis()
        pipe = client.pipeline()
        k = self._key(key)
        await pipe.incr(k)
        if ttl:
            await pipe.expire(k, ttl)
        results = await pipe.execute()
        return results[0]

    async def get_or_set(self, key: str, factory, ttl: int | None = None) -> Any:
        """Return cached value or call factory(), cache it, and return."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await factory() if callable(factory) else factory
        await self.set(key, value, ttl)
        return value
