"""
Promotion code rate limiter service.
Provides a decorator for rate limiting promotion code redemption attempts.
"""

from functools import wraps
from http import HTTPStatus
from typing import Any, Callable
from uuid import UUID

from redis.asyncio import Redis

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.redis import RateLimiter, get_redis
from virtual_labs.shared.utils.auth import get_user_id_from_auth


def rate_limit_promotion_redemption(
    prefix: str = "promotion_code",
    max_attempts: int = 3,
    window_seconds: int = 1800,  # 30 minutes
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to rate limit promotion code redemption attempts.

    Limits users to a specific number of redemption attempts within a time window.
    Tracks both successful and failed attempts.

    Args:
        max_attempts: Maximum number of attempts allowed (default: 3)
        window_seconds: Time window in seconds (default: 1800 = 30 minutes)

    Raises:
        VliError: When rate limit is exceeded (429 Too Many Requests)
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract auth and rate_limiter from kwargs
            auth = kwargs.get("auth")
            if not isinstance(auth, tuple) or len(auth) != 2:
                raise VliError(
                    error_code=VliErrorCode.INVALID_REQUEST,
                    message="Invalid authentication data",
                    http_status_code=HTTPStatus.UNAUTHORIZED,
                )
            redis: Redis = await get_redis()
            rate_limiter: RateLimiter = RateLimiter(redis, prefix)

            user_id: UUID = get_user_id_from_auth(auth)

            rate_limit_key = rate_limiter.build_universal_key("redeem", str(user_id))
            current_count = await rate_limiter.get_count(rate_limit_key)

            if current_count is not None and current_count >= max_attempts:
                ttl = await rate_limiter.get_ttl(rate_limit_key)
                raise VliError(
                    error_code=VliErrorCode.LIMIT_EXCEEDED,
                    http_status_code=HTTPStatus.TOO_MANY_REQUESTS,
                    details=f"Rate limit exceeded. You can only redeem promotion codes {max_attempts} times per {window_seconds // 60} minutes. ",
                    message=f"You have exceeded the attempts limit, Try again in {ttl // 60} mins.",
                    data={
                        "retry_after": ttl,
                        "max_attempts": max_attempts,
                        "window_seconds": window_seconds,
                    },
                )

            try:
                result = await func(*args, **kwargs)

                if current_count is None:
                    await rate_limiter.set(rate_limit_key, 1, ttl=window_seconds)
                else:
                    await rate_limiter.increment(rate_limit_key)

                return result

            except Exception as e:
                if current_count is None:
                    await rate_limiter.set(rate_limit_key, 1, ttl=window_seconds)
                else:
                    await rate_limiter.increment(rate_limit_key)

                raise e

        return wrapper

    return decorator
