from typing import Optional

from fastapi import Depends
from redis.asyncio import Redis

from virtual_labs.infrastructure.settings import settings

# Singleton Redis client (optional, initialized lazily)
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Dependency to provide an async Redis client."""
    global _redis_client

    if _redis_client is None:
        redis_host = settings.REDIS_HOST
        redis_port = settings.REDIS_PORT

        _redis_client = Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            auto_close_connection_pool=False,
        )

    try:
        await _redis_client.ping()
    except Exception:
        await _redis_client.close()
        _redis_client = Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            auto_close_connection_pool=False,
        )

    return _redis_client


class RateLimiter:
    """Utility class for managing rate limits in Redis."""

    def __init__(self, redis: Redis, prefix: str = "rate_limit"):
        self.redis = redis
        self.prefix = prefix

    def build_key(self, action: str, user_id: str, email: str) -> str:
        """Construct a Redis key based on action, user_id, and email."""
        return f"{self.prefix}:{action}:{user_id}:{email}"

    async def get_count(self, key: str) -> Optional[int]:
        """Get the current count for a key, or None if it doesn't exist."""
        count = await self.redis.get(key)
        return int(count) if count is not None else None

    async def set(self, key: str, value: int, ttl: int = 3600) -> None:
        """Set a value for a key with an optional TTL (default 1 hour)."""
        await self.redis.set(key, value, ex=ttl)

    async def increment(self, key: str) -> None:
        """Increment the count for a key."""
        await self.redis.incr(key)

    async def get_ttl(self, key: str) -> int:
        """Get the remaining TTL in seconds for a key."""
        return int(await self.redis.ttl(key))


async def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    """Dependency to provide RateLimiter instance."""
    return RateLimiter(redis)
