from http import HTTPStatus as status
from typing import Optional, Tuple

from fastapi import Depends

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.email import (
    EmailVerificationPayload,
    InitiateEmailVerificationPayload,
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis import RateLimiter, get_redis
from virtual_labs.infrastructure.settings import settings


async def get_initiate_rate_limiter() -> RateLimiter:
    """Get rate limiter for email initiation."""
    redis = await get_redis()
    return RateLimiter(redis, prefix="email_validation")


async def get_verify_rate_limiter() -> RateLimiter:
    """Get rate limiter for email verification."""
    redis = await get_redis()
    return RateLimiter(redis, prefix="email_validation")


async def rate_limit_initiate(
    payload: InitiateEmailVerificationPayload,
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    rl: RateLimiter = Depends(get_initiate_rate_limiter),
) -> Optional[int]:
    """Enforce rate limit for initiating email verification (e.g., 3/1h)."""

    user_id = auth[0].sub
    key = rl.build_key_by_email("initiate", user_id, payload.email)
    count = await rl.get_count(key)

    if count is None:
        count = await rl.set(key, 1, ttl=settings.LOCK_TIME_SECONDS)  # 1h
    else:
        count = await rl.increment(key)

    if count >= settings.MAX_INIT_ATTEMPTS:
        remaining_seconds = await rl.get_ttl(key)
        remaining_time = remaining_seconds // 60 if remaining_seconds > 0 else 0
        raise VliError(
            error_code=VliErrorCode.RATE_LIMIT_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Failed to initiate email verification",
            data={
                "message": f"Too many attempts. Try again in {remaining_time} minutes"
                if remaining_time > 0
                else "Rate limit exceeded: too many email verification initiations ",
                "status": VerificationCodeStatus.LOCKED.value,
                "remaining_time": remaining_time if remaining_time > 0 else None,
                "remaining_attempts": None,
            },
        )

    return await rl.get_count(key)


async def rate_limit_verify(
    payload: EmailVerificationPayload,
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    rl: RateLimiter = Depends(get_verify_rate_limiter),
) -> Optional[int]:
    """Enforce rate limit for verifying email codes (e.g. 5/1h)."""

    user_id = auth[0].sub
    key = rl.build_key_by_email("verify", user_id, payload.email)
    count = await rl.get_count(key)

    if count is None:
        count = await rl.set(key, 1, ttl=settings.LOCK_TIME_SECONDS)  # 1h
    else:
        count = await rl.increment(key)

    if count >= settings.MAX_VERIFY_ATTEMPTS:
        remaining_seconds = await rl.get_ttl(key)
        remaining_time = remaining_seconds // 60 if remaining_seconds > 0 else 0
        raise VliError(
            error_code=VliErrorCode.RATE_LIMIT_ERROR,
            http_status_code=status.TOO_MANY_REQUESTS,
            message="Failed to verify email verification code",
            data={
                "message": f"Too many incorrect attempts. Code verification locked for {remaining_time} minutes"
                if remaining_time > 0
                else "Rate limit exceeded: too many email verification failed",
                "status": VerificationCodeStatus.LOCKED.value,
                "remaining_time": remaining_time if remaining_time > 0 else None,
                "remaining_attempts": None,
            },
        )

    return count
