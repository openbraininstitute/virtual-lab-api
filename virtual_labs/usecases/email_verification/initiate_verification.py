import secrets
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
    CODE_LENGTH,
    LOCK_TIME_MINUTES,
    MAX_ATTEMPTS,
    EmailVerificationCode,
    VerificationCodeEmailDetails,
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.email.verification_code_email import (
    send_verification_code_email,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.email_verification import (
    EmailValidationMutationRepository,
    EmailValidationQueryRepository,
)
from virtual_labs.repositories.labs import get_virtual_lab_by_definition_tuple


def _generate_verification_code() -> EmailVerificationCode:
    """Generate secure 6-digit numeric code"""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def initiate_email_verification(
    session: AsyncSession,
    *,
    email: EmailStr,
    virtual_lab_name: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    """Start email verification process"""
    es = EmailValidationQueryRepository(session)
    esm = EmailValidationMutationRepository(session)

    user_id = UUID(auth[0].sub)

    try:
        # Check if the email (user, virtual-lab) is already verified
        # the combination of email, user_id, and virtual_lab_name should be unique
        if await es.check_email_verified(
            email=email,
            user_id=user_id,
            virtual_lab_name=virtual_lab_name,
        ):
            if await get_virtual_lab_by_definition_tuple(
                session,
                user_id,
                name=virtual_lab_name,
            ):
                raise EmailVerificationException(
                    "Virtual lab already registered with this details",
                    data={
                        "message": "Virtual lab already registered with this details",
                        "status": VerificationCodeStatus.REGISTERED,
                        "remaining_time": None,
                        "remaining_attempts": None,
                    },
                )

        now = datetime.utcnow()

        verification_code_entry = await es.get_latest_verification_code_entry(
            email=email,
            user_id=user_id,
            virtual_lab_name=virtual_lab_name,
        )

        # Reset lock if lock time has passed
        if (
            verification_code_entry
            and verification_code_entry.locked_until
            and now > verification_code_entry.locked_until
        ):
            verification_code_entry.locked_until = None
            verification_code_entry.generation_attempts = 0
            await session.commit()
            await session.refresh(verification_code_entry)

        if verification_code_entry:
            # Check if the account is locked due to too many failed attempts
            # and the lock time has not passed yet, return the remaining time
            if (
                verification_code_entry.locked_until
                and verification_code_entry.locked_until > now
            ):
                remaining_time = (
                    verification_code_entry.locked_until - now
                ).seconds // 60
                raise EmailVerificationException(
                    f"Too many attempts. Try again in {remaining_time} minutes",
                    data={
                        "message": f"Too many attempts. Try again in {remaining_time} minutes",
                        "status": VerificationCodeStatus.LOCKED,
                        "remaining_time": remaining_time,
                        "remaining_attempts": MAX_ATTEMPTS
                        - verification_code_entry.generation_attempts,
                    },
                )
            # update attempts and lock the account if the attempts exceed the limit
            verification_code_entry.generation_attempts += 1
            if verification_code_entry.generation_attempts >= 3:
                verification_code_entry.locked_until = datetime.utcnow() + timedelta(
                    minutes=LOCK_TIME_MINUTES
                )

            await session.commit()
            await session.refresh(verification_code_entry)

        # Generate a new verification code if the previous one has expired
        if verification_code_entry and verification_code_entry.expires_at >= now:
            code = verification_code_entry.code
            expire_at_minutes = int(
                (verification_code_entry.expires_at - now).total_seconds() / 60
            )
        else:
            code = _generate_verification_code()
            verification_code_entry = await esm.generate_verification_token(
                email, user_id, virtual_lab_name, code, 1
            )
            expire_at_minutes = int(
                (verification_code_entry.expires_at - now).total_seconds() / 60
            )

        email_details = VerificationCodeEmailDetails(
            recipient=email,
            code=code,
            virtual_lab_name=virtual_lab_name,
            expire_at=f"{expire_at_minutes}",
        )

        await send_verification_code_email(details=email_details)

    except EmailVerificationException as e:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=status.BAD_REQUEST,
            message=str(e),
            data=e.data,
        )
    except SQLAlchemyError as ex:
        logger.error(f"Failed to initiate email verification for {email}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Failed to initiate email verification",
        )
    except Exception as ex:
        print(f"{ex=}")
        logger.error(f"Error during email verification initiation for {email}: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Error during email verification initiation",
        )
    else:
        return VliResponse.new(
            message="Verification code email sent successfully",
            data={
                "message": "Verification code email sent successfully",
                "status": VerificationCodeStatus.CODE_SENT,
                "remaining_time": None,
                "remaining_attempts": None,
            },
        )
