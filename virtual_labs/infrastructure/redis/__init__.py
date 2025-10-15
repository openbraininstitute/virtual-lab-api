from typing import Optional, cast

from fastapi import Depends
from redis.asyncio import ConnectionPool, Redis

from virtual_labs.infrastructure.settings import settings

# Singleton Redis client and connection pool (initialized lazily)
_redis_client: Redis | None = None
_connection_pool: ConnectionPool | None = None


async def get_redis() -> Redis:
    """Dependency to provide an async Redis client."""
    global _redis_client, _connection_pool

    redis_host = settings.REDIS_HOST
    redis_port = settings.REDIS_PORT

    if _connection_pool is None:
        _connection_pool = ConnectionPool(
            host=redis_host,
            port=redis_port,
            password=None,
            decode_responses=True,
        )

    if _redis_client is None:
        _redis_client = Redis(connection_pool=_connection_pool)

    try:
        await _redis_client.ping()
    except Exception:
        await _redis_client.close()
        _redis_client = Redis(connection_pool=_connection_pool)

    return _redis_client


class RateLimiter:
    """Utility class for managing rate limits in Redis."""

    def __init__(self, redis: Redis, prefix: str = "rate_limit"):
        self.redis = redis
        self.prefix = prefix

    def build_key_by_email(self, action: str, user_id: str, email: str) -> str:
        """Construct a Redis key based on action, user_id, and email."""
        return f"{self.prefix}:{action}:{user_id}:{email}"

    def build_universal_key(self, action: str, user_id: str) -> str:
        """Construct a Redis key based on action, user_id."""
        return f"{self.prefix}:{action}:{user_id}"

    async def get_count(self, key: str) -> Optional[int]:
        """Get the current count for a key, or None if it doesn't exist."""
        count = await self.redis.get(key)
        return int(count) if count is not None else None

    async def set(self, key: str, value: int, ttl: int = 3600) -> int:
        """Set a value for a key with an optional TTL (default 1 hour)."""
        _value = await self.redis.set(key, value, ex=ttl)
        return cast(int, _value)

    async def increment(self, key: str) -> int:
        """Increment the count for a key."""
        _value = await self.redis.incr(key)
        return cast(int, _value)

    async def get_ttl(self, key: str) -> int:
        """Get the remaining TTL in seconds for a key."""
        return int(await self.redis.ttl(key))


async def get_rate_limiter(
    redis: Redis = Depends(get_redis),
    prefix: str = "rate_limit",
) -> RateLimiter:
    """Dependency to provide RateLimiter instance."""
    return RateLimiter(redis, prefix)
