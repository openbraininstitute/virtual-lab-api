import asyncio
from datetime import datetime, timezone
from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from loguru import logger
from pydantic import EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_verification import EmailVerificationException
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.email import (
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis import RateLimiter
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.email_verification_repo import (
    EmailValidationQueryRepository,
)
from virtual_labs.repositories.labs import update_virtual_lab_email_status
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
    es = EmailValidationQueryRepository(session)
    user_id = get_user_id_from_auth(auth)

    rd_key = rl.build_key_by_email(
        "verify",
        str(user_id),
        str(virtual_lab_id),
        email,
    )

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        vlab = await lab_repository.get_virtual_lab_soft(session, lab_id=virtual_lab_id)

        if vlab and vlab.email_verified:
            raise EmailVerificationException(
                "Virtual lab already registered with this details",
                data={
                    "message": "Email already verified for this virtual lab",
                    "status": VerificationCodeStatus.REGISTERED.value,
                    "remaining_time": None,
                    "remaining_attempts": None,
                },
            )

        if not (
            verification_code_entry := await es.get_verification_code(
                virtual_lab_id=virtual_lab_id,
                user_id=user_id,
                email=email,
            )
        ):
            raise EmailVerificationException(
                "No active verification code found",
                data={
                    "message": "No active verification code found or code expired",
                    "status": VerificationCodeStatus.EXPIRED.value,
                    "remaining_time": None,
                    "remaining_attempts": None,
                },
            )

        if verification_code_entry.code != code.strip():
            attempts = await rl.get_count(rd_key)
            remaining_attempts = settings.MAX_VERIFY_ATTEMPTS - (attempts or 0)
            print(
                "———rd_key",
                rd_key,
                "@@attempts",
                attempts,
                "@@remaining_attempts",
                remaining_attempts,
            )

            raise EmailVerificationException(
                f"Invalid code, {remaining_attempts} attempts remaining",
                data={
                    "message": f"Invalid code, {remaining_attempts} attempts remaining",
                    "status": VerificationCodeStatus.NOT_MATCH.value,
                    "remaining_time": None,
                    "remaining_attempts": remaining_attempts,
                },
            )

        verification_code_entry.is_verified = True
        verification_code_entry.verified_at = now

        await asyncio.gather(
            rl.delete(rd_key),
            update_virtual_lab_email_status(
                db=session,
                lab_id=virtual_lab_id,
                email_status=True,
            ),
        )

        await session.commit()
        await session.refresh(verification_code_entry)

        return VliResponse.new(
            message="Email verified successfully",
            data={
                "message": "Email verified successfully",
                "status": VerificationCodeStatus.VERIFIED.value,
                "remaining_attempts": None,
                "remaining_time": None,
                "verified_at": verification_code_entry.verified_at,
            },
        )
    except EmailVerificationException as e:
        raise VliError(
            data=e.data,
            http_status_code=status.BAD_REQUEST,
            error_code=VliErrorCode.INVALID_REQUEST,
            message=str(e),
        )

    except SQLAlchemyError as e:
        logger.error(f"Database error during email verification for {email}: {e}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Failed to verify email code",
        )

    except Exception as ex:
        logger.error(f"Unexpected error during email verification for {email}: {ex}")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during email verification",
        )
