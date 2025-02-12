from datetime import datetime, timedelta
from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from loguru import logger
from pydantic import EmailStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.email_verification import EmailVerificationException
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.email import LOCK_TIME_MINUTES, MAX_ATTEMPTS
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.email_verification import (
    EmailValidationQueryRepository,
)


async def verify_email_code(
    session: AsyncSession,
    *,
    email: EmailStr,
    virtual_lab_name: str,
    code: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    es = EmailValidationQueryRepository(session)
    user_id = auth[0].sub
    print(f"User ID: {user_id}")
    try:
        now = datetime.utcnow()
        verification_code_entry = await es.get_verification_code(
            email,
            user_id,
            virtual_lab_name,
        )
        if not verification_code_entry:
            raise EmailVerificationException("No active verification code found")

        # Reset lock if time has passed
        if (
            verification_code_entry.locked_until
            and now > verification_code_entry.locked_until
        ):
            verification_code_entry.locked_until = None
            verification_code_entry.attempts = 0
            await session.commit()

        # Check if the account is locked due to too many failed attempts
        if (
            verification_code_entry.locked_until
            and verification_code_entry.locked_until > now
        ):
            remaining_time = (verification_code_entry.locked_until - now).seconds // 60
            raise EmailVerificationException(
                f"Too many attempts. Try again in {remaining_time} minutes",
                data={
                    "remaining_time": remaining_time,
                    "remaining_attempts": MAX_ATTEMPTS,
                    "locked": True,
                },
            )

        # Validate the user-provided code
        if verification_code_entry.token != code.strip():
            # Increment the failed attempt counter
            verification_code_entry.attempts += 1

            # Lock the account if the maximum number of attempts is reached
            if verification_code_entry.attempts >= MAX_ATTEMPTS:
                verification_code_entry.locked_until = now + timedelta(
                    minutes=LOCK_TIME_MINUTES
                )
                await session.commit()
                # calculate the remaining time in minutes
                remaining_time = (
                    verification_code_entry.locked_until - now
                ).seconds // 60
                raise EmailVerificationException(
                    "Too many incorrect attempts. Code locked for 15 minutes",
                    data={
                        "remaining_time": remaining_time,
                        "remaining_attempts": 0,
                        "locked": True,
                    },
                )

            await session.commit()
            # Calculate remaining attempts and raise an appropriate error
            remaining_attempts = MAX_ATTEMPTS - verification_code_entry.attempts
            if remaining_attempts > 0:
                raise EmailVerificationException(
                    f"Invalid code. {remaining_attempts} attempts remaining",
                    data={
                        "remaining_attempts": remaining_attempts,
                        "remaining_time": 0,
                        "locked": False,
                    },
                )

        # Mark the token as used and commit the changes
        verification_code_entry.is_verified = True
        await session.commit()

        # Return a success response (assuming Response is a custom class)
        return VliResponse.new(
            message="Email verified successfully",
            data={
                "email": email,
                "verified_at": now,
                "is_verified": True,
            },
        )
    except EmailVerificationException as e:
        return VliError(
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
