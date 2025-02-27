from datetime import datetime, timedelta
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
    LOCK_TIME_MINUTES,
    MAX_ATTEMPTS,
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.email_verification import (
    EmailValidationQueryRepository,
)
from virtual_labs.repositories.labs import get_virtual_lab_by_definition_tuple


async def verify_email_code(
    session: AsyncSession,
    *,
    email: EmailStr,
    virtual_lab_name: str,
    code: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    es = EmailValidationQueryRepository(session)

    user_id = UUID(auth[0].sub)

    try:
        now = datetime.utcnow()

        if await get_virtual_lab_by_definition_tuple(
            session,
            user_id,
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
            email,
            user_id,
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

        # Reset lock if time has passed
        if (
            verification_code_entry.locked_until
            and now > verification_code_entry.locked_until
        ):
            verification_code_entry.locked_until = None
            verification_code_entry.verification_attempts = 0
            await session.commit()
            await session.refresh(verification_code_entry)

        # Check if the account is locked due to too many failed attempts
        if (
            verification_code_entry.locked_until
            and verification_code_entry.locked_until > now
        ):
            remaining_time = (verification_code_entry.locked_until - now).seconds // 60
            raise EmailVerificationException(
                f"Too many attempts. Try again in {remaining_time} minutes",
                data={
                    "message": f"Too many attempts. Try again in {remaining_time} minutes",
                    "status": VerificationCodeStatus.LOCKED.value,
                    "remaining_time": remaining_time,
                    "remaining_attempts": 0,
                },
            )

        # Validate the user-provided code
        if verification_code_entry.code != code.strip():
            verification_code_entry.verification_attempts += 1

            # Lock the account if the maximum number of attempts is reached
            if verification_code_entry.verification_attempts >= MAX_ATTEMPTS:
                verification_code_entry.locked_until = now + timedelta(
                    minutes=LOCK_TIME_MINUTES
                )
                await session.commit()
                await session.refresh(verification_code_entry)
                remaining_time = (
                    verification_code_entry.locked_until - now
                ).seconds // 60
                raise EmailVerificationException(
                    "Too many incorrect attempts. Code locked for 15 minutes",
                    data={
                        "message": "Too many incorrect attempts. sending code locked for 15 minutes",
                        "status": VerificationCodeStatus.LOCKED.value,
                        "remaining_time": remaining_time,
                        "remaining_attempts": 0,
                    },
                )

            await session.commit()
            await session.refresh(verification_code_entry)
            # Calculate remaining attempts and raise an appropriate error
            remaining_attempts = (
                MAX_ATTEMPTS - verification_code_entry.verification_attempts
            )
            if remaining_attempts > 0:
                raise EmailVerificationException(
                    f"Invalid code. {remaining_attempts} attempts remaining",
                    data={
                        "message": f"Invalid code. {remaining_attempts} attempts remaining",
                        "status": VerificationCodeStatus.LOCKED.value,
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
