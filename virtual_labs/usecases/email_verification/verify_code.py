from datetime import datetime
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
from virtual_labs.repositories.email_verification_repo import (
    EmailValidationQueryRepository,
)
from virtual_labs.repositories.labs import get_virtual_lab_by_definition_tuple


async def verify_email_code(
    session: AsyncSession,
    rl: RateLimiter,
    *,
    email: EmailStr,
    virtual_lab_name: str,
    code: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    es = EmailValidationQueryRepository(session)

    user_id = UUID(auth[0].sub)
    rd_key = rl.build_key("verify", str(user_id), email)

    try:
        now = datetime.utcnow()

        if await get_virtual_lab_by_definition_tuple(
            session,
            user_id,
            email=email,
            name=virtual_lab_name,
        ):
            raise EmailVerificationException(
                "Virtual lab already registered with this details",
                data={
                    "message": "Virtual lab already registered with this details",
                    "status": VerificationCodeStatus.REGISTERED.value,
                    "remaining_time": None,
                    "remaining_attempts": None,
                },
            )

        verification_code_entry = await es.get_verification_code(
            user_id,
            email,
            virtual_lab_name,
        )

        if not verification_code_entry:
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
