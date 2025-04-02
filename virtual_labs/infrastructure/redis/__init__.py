from typing import Dict

from redis.asyncio import Redis

from virtual_labs.infrastructure.settings import settings

# Singleton Redis client (optional, initialized lazily)
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Dependency to provide an async Redis client."""
    global _redis_client

    redis_host = settings.REDIS_HOST
    redis_port = settings.REDIS_PORT
    if _redis_client is None:
        _redis_client = Redis(
            host=redis_host,
            port=redis_port,
            password=None,
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
            password=None,
            decode_responses=True,
            auto_close_connection_pool=False,
        )

    return _redis_client


async def get_health_status(redis_client: Redis) -> Dict[str, str | None]:
    """Check Redis connection health."""
    try:
        response = await redis_client.ping()
        info = await redis_client.info()
        redis_version = info.get("redis_version", "unknown")

        if response:
            return {"status": "ok", "redis": "up", "version": redis_version}
        else:
            return {
                "status": "degraded",
                "redis": "ping failed",
                "version": redis_version,
            }
    except Exception as e:
        return {"status": "degraded", "redis": f"error {str(e)}", "version": None}
