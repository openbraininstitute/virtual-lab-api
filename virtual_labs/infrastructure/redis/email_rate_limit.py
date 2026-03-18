from http import HTTPStatus as status
from typing import Annotated, Optional, Tuple

from fastapi import Depends, Header
from pydantic import UUID4

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
    virtual_lab_id: Annotated[UUID4, Header()],
    payload: InitiateEmailVerificationPayload,
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    rl: RateLimiter = Depends(get_initiate_rate_limiter),
) -> Optional[int]:
    """Enforce rate limit for initiating email verification: 3 requests per hour."""
    user_id = auth[0].sub
    key = rl.build_key_by_email("initiate", user_id, str(virtual_lab_id), payload.email)

    count = await rl.get_count(key)

    if count is None:
        await rl.set(key, 1, ttl=settings.INITIATE_LOCK_SECONDS)
        return 1

    if int(count) >= settings.MAX_INIT_ATTEMPTS:
        remaining_seconds = await rl.get_ttl(key)
        raise VliError(
            error_code=VliErrorCode.RATE_LIMIT_ERROR,
            http_status_code=status.TOO_MANY_REQUESTS,
            message="Too many code requests",
            data={
                "message": f"Too many attempts. Try again in {remaining_seconds} seconds",
                "status": VerificationCodeStatus.LOCKED.value,
                "remaining_time": remaining_seconds
                if remaining_seconds and remaining_seconds > 0
                else None,
                "remaining_attempts": 0,
            },
        )

    new_count = await rl.increment(key)
    return new_count


async def rate_limit_verify(
    virtual_lab_id: Annotated[UUID4, Header()],
    payload: EmailVerificationPayload,
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
    rl: RateLimiter = Depends(get_verify_rate_limiter),
) -> Optional[int]:
    """Enforce rate limit for verifying email codes: 5 attempts per 15 minutes."""
    user_id = auth[0].sub
    verify_key = rl.build_key_by_email(
        "verify", user_id, str(virtual_lab_id), payload.email
    )

    count = await rl.get_count(verify_key)

    if count is None or count == 0:
        await rl.set(verify_key, 1, ttl=settings.VERIFY_LOCK_SECONDS)
        return 1

    if int(count) >= settings.MAX_VERIFY_ATTEMPTS:
        remaining_seconds = await rl.get_ttl(verify_key)
        raise VliError(
            error_code=VliErrorCode.RATE_LIMIT_ERROR,
            http_status_code=status.TOO_MANY_REQUESTS,
            message="Too many verification attempts",
            data={
                "message": f"Too many incorrect attempts. Locked for {remaining_seconds} seconds",
                "status": VerificationCodeStatus.LOCKED.value,
                "remaining_time": remaining_seconds
                if remaining_seconds and remaining_seconds > 0
                else None,
                "remaining_attempts": 0,
            },
        )

    new_count = await rl.increment(verify_key)
    return new_count
