import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.email import (
    CODE_LENGTH,
    EmailVerificationCode,
    VerificationCodeEmailDetails,
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.db.models import EmailVerification
from virtual_labs.infrastructure.email.verification_code_email import (
    send_verification_code_email,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis import RateLimiter
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


def _generate_verification_code() -> EmailVerificationCode:
    """Generate secure 6-digit numeric code."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def initiate_email_verification(
    session: AsyncSession,
    rl: RateLimiter,
    *,
    email: EmailStr,
    virtual_lab_id: UUID,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Start email verification process.

    Redis keys used:
      - code:{user}:{lab}:{email}   → stores the OTP code (TTL 1h)
      - initiate:{user}:{lab}:{email} → request counter (TTL 1h, managed by rate_limit_initiate dependency)
    """
    user_id = get_user_id_from_auth(auth)

    code_key = rl.build_key_by_email("code", str(user_id), str(virtual_lab_id), email)
    initiate_key = rl.build_key_by_email(
        "initiate", str(user_id), str(virtual_lab_id), email
    )

    try:
        virtual_lab = await lab_repository.get_undeleted_virtual_lab(
            session, virtual_lab_id
        )

        existing_code = await rl.get(code_key)
        is_new_code = False

        if existing_code:
            code = existing_code
            code_ttl = await rl.get_ttl(code_key)
        else:
            code = _generate_verification_code()
            await rl.set(code_key, code, ttl=settings.INITIATE_LOCK_SECONDS)
            code_ttl = settings.INITIATE_LOCK_SECONDS
            is_new_code = True

        email_details = VerificationCodeEmailDetails(
            recipient=email,
            code=code,
            virtual_lab_id=virtual_lab_id,
            virtual_lab_name=virtual_lab.name,
            expire_at=f"{code_ttl}",
        )

        await send_verification_code_email(details=email_details)

        # audit: persist after we're done reading from the session
        if is_new_code:
            try:
                verification_record = EmailVerification(
                    user_id=user_id,
                    virtual_lab_id=virtual_lab_id,
                    email=email,
                    code=code,
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=settings.INITIATE_LOCK_SECONDS),
                )
                session.add(verification_record)
                await session.commit()
            except Exception as audit_err:
                logger.warning(
                    f"Failed to persist email verification audit record: {audit_err}"
                )

        attempts = await rl.get_count(initiate_key) or 0
        remaining_attempts = max(settings.MAX_INIT_ATTEMPTS - attempts, 0)

        return VliResponse.new(
            message="Verification code email sent successfully",
            data={
                "message": "Verification code email sent successfully",
                "status": VerificationCodeStatus.CODE_SENT.value
                if remaining_attempts > 0
                else VerificationCodeStatus.LOCKED.value,
                "remaining_time": code_ttl,
                "remaining_attempts": remaining_attempts,
            },
        )
    except VliError:
        raise
    except Exception as ex:
        logger.error(f"Error during email verification initiation for {email}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during email verification initiation",
        )


async def get_initiate_status(
    rl: RateLimiter,
    *,
    virtual_lab_id: UUID,
    email: EmailStr,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Can the user request a (new) code?

    Returns:
      - LOCKED   : 3 requests/hour exceeded, show countdown
      - CODE_SENT: code still alive, show "check your email" + TTL
      - EXPIRED  : code was sent before but expired, show "request new code"
      - WAITING  : nothing happened yet, show "request code" button
    """
    user_id = get_user_id_from_auth(auth)

    initiate_key = rl.build_key_by_email(
        "initiate", str(user_id), str(virtual_lab_id), email
    )
    code_key = rl.build_key_by_email("code", str(user_id), str(virtual_lab_id), email)

    try:
        count = await rl.get_count(initiate_key) or 0
        initiate_ttl = await rl.get_ttl(initiate_key)
        code_ttl = await rl.get_ttl(code_key)
        has_active_code = code_ttl is not None and code_ttl > 0

        if count >= settings.MAX_INIT_ATTEMPTS:
            return VliResponse.new(
                message="Initiate status",
                data={
                    "message": "Too many code requests, please wait",
                    "status": VerificationCodeStatus.LOCKED.value,
                    "remaining_time": initiate_ttl
                    if initiate_ttl and initiate_ttl > 0
                    else None,
                    "remaining_attempts": 0,
                },
            )

        remaining_attempts = settings.MAX_INIT_ATTEMPTS - count

        if has_active_code:
            return VliResponse.new(
                message="Initiate status",
                data={
                    "message": "Verification code is active",
                    "status": VerificationCodeStatus.CODE_SENT.value,
                    "remaining_time": code_ttl,
                    "remaining_attempts": remaining_attempts,
                },
            )

        if count > 0:
            return VliResponse.new(
                message="Initiate status",
                data={
                    "message": "Verification code has expired",
                    "status": VerificationCodeStatus.EXPIRED.value,
                    "remaining_time": None,
                    "remaining_attempts": remaining_attempts,
                },
            )

        return VliResponse.new(
            message="Initiate status",
            data={
                "message": "No verification code requested yet",
                "status": VerificationCodeStatus.WAITING.value,
                "remaining_time": None,
                "remaining_attempts": remaining_attempts,
            },
        )
    except Exception as ex:
        logger.error(f"Error fetching initiate status for {email}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error fetching initiate status",
        )


async def get_verify_status(
    rl: RateLimiter,
    *,
    virtual_lab_id: UUID,
    email: EmailStr,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Can the user submit a code?

    Returns:
      - LOCKED   : 5 attempts/15min exceeded, show countdown
      - CODE_SENT: code is active, user can still attempt, show input form
      - EXPIRED  : no active code to verify against, prompt to request a new one
    """
    user_id = get_user_id_from_auth(auth)

    verify_key = rl.build_key_by_email(
        "verify", str(user_id), str(virtual_lab_id), email
    )
    code_key = rl.build_key_by_email("code", str(user_id), str(virtual_lab_id), email)

    try:
        count = await rl.get_count(verify_key) or 0
        verify_ttl = await rl.get_ttl(verify_key)
        code_ttl = await rl.get_ttl(code_key)
        has_active_code = code_ttl is not None and code_ttl > 0

        if count >= settings.MAX_VERIFY_ATTEMPTS:
            return VliResponse.new(
                message="Verify status",
                data={
                    "message": "Too many incorrect attempts, please wait",
                    "status": VerificationCodeStatus.LOCKED.value,
                    "remaining_time": verify_ttl
                    if verify_ttl and verify_ttl > 0
                    else None,
                    "remaining_attempts": 0,
                },
            )

        remaining_attempts = settings.MAX_VERIFY_ATTEMPTS - count

        if has_active_code:
            return VliResponse.new(
                message="Verify status",
                data={
                    "message": "Verification code is active, enter your code",
                    "status": VerificationCodeStatus.CODE_SENT.value,
                    "remaining_time": code_ttl,
                    "remaining_attempts": remaining_attempts,
                },
            )

        return VliResponse.new(
            message="Verify status",
            data={
                "message": "No active code, request a new one",
                "status": VerificationCodeStatus.EXPIRED.value,
                "remaining_time": None,
                "remaining_attempts": remaining_attempts,
            },
        )
    except Exception as ex:
        logger.error(f"Error fetching verify status for {email}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error fetching verify status",
        )
