from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.email import VerificationCodeStatus
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis import RateLimiter
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.labs import update_virtual_lab_email_status
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.services.stripe_customer import ensure_stripe_customer
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def verify_email_code(
    session: AsyncSession,
    rl: RateLimiter,
    *,
    email: EmailStr,
    virtual_lab_id: UUID,
    code: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Verify the OTP code against the value stored in Redis.

    Redis keys used:
      - code:{user}:{lab}:{email}   → the stored OTP (TTL 1h)
      - verify:{user}:{lab}:{email} → attempt counter (TTL 15min, managed by rate_limit_verify dependency)
    """
    user_id = get_user_id_from_auth(auth)

    code_key = rl.build_key_by_email("code", str(user_id), str(virtual_lab_id), email)
    verify_key = rl.build_key_by_email(
        "verify", str(user_id), str(virtual_lab_id), email
    )
    user_query_repo = UserQueryRepository()

    try:
        vlab = await lab_repository.get_virtual_lab_soft(session, lab_id=virtual_lab_id)

        if vlab and vlab.email_verified:
            raise VliError(
                error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
                http_status_code=status.BAD_REQUEST,
                message="Email already verified for this virtual lab",
                data={
                    "message": "Email already verified for this virtual lab",
                    "status": VerificationCodeStatus.REGISTERED.value,
                    "remaining_time": None,
                    "remaining_attempts": None,
                },
            )

        stored_code = await rl.get(code_key)
        if not stored_code:
            raise VliError(
                error_code=VliErrorCode.INVALID_REQUEST,
                http_status_code=status.BAD_REQUEST,
                message="No active verification code found or code expired",
                data={
                    "message": "No active verification code found or code expired",
                    "status": VerificationCodeStatus.EXPIRED.value,
                    "remaining_time": None,
                    "remaining_attempts": None,
                },
            )

        if stored_code != code.strip():
            attempts = await rl.get_count(verify_key) or 0
            remaining = max(settings.MAX_VERIFY_ATTEMPTS - attempts, 0)
            raise VliError(
                error_code=VliErrorCode.INVALID_REQUEST,
                http_status_code=status.BAD_REQUEST,
                message=f"Invalid code, {remaining} attempts remaining",
                data={
                    "message": f"Invalid code, {remaining} attempts remaining",
                    "status": VerificationCodeStatus.NOT_MATCH.value
                    if remaining > 0
                    else VerificationCodeStatus.LOCKED.value,
                    "remaining_time": None,
                    "remaining_attempts": remaining,
                },
            )

        await update_virtual_lab_email_status(
            db=session,
            lab_id=virtual_lab_id,
            email_status=True,
        )

        user = await user_query_repo.get_user(user_id=str(user_id))
        await ensure_stripe_customer(
            session=session,
            email=email,
            user_id=user_id,
            name=f"{user.get('firstName', '')} {user.get('lastName', '')}",
        )

        await rl.delete(code_key)
        await rl.delete(verify_key)

        return VliResponse.new(
            message="Email verified successfully",
            data={
                "message": "Email verified successfully",
                "status": VerificationCodeStatus.VERIFIED.value,
                "remaining_time": None,
                "remaining_attempts": None,
            },
        )
    except VliError:
        raise
    except Exception as ex:
        logger.error(f"Unexpected error during email verification for {email}: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during email verification",
        )
