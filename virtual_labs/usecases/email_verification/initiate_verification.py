import secrets
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
    CODE_LENGTH,
    EmailVerificationCode,
    VerificationCodeEmailDetails,
    VerificationCodeStatus,
)
from virtual_labs.infrastructure.email.verification_code_email import (
    send_verification_code_email,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.redis import RateLimiter
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.email_verification_repo import (
    EmailValidationMutationRepository,
    EmailValidationQueryRepository,
)


def _generate_verification_code() -> EmailVerificationCode:
    """Generate secure 6-digit numeric code"""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def initiate_email_verification(
    session: AsyncSession,
    rl: RateLimiter,
    *,
    email: EmailStr,
    virtual_lab_name: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    """Start email verification process"""
    es = EmailValidationQueryRepository(session)
    esm = EmailValidationMutationRepository(session)

    user_id = UUID(auth[0].sub)
    rd_key = rl.build_key_by_email("initiate", str(user_id), email)

    try:
        verification_code_entry = await es.get_latest_verification_code_entry(
            email=email,
            user_id=user_id,
        )

        # Generate a new verification code if the previous one has expired
        now = datetime.utcnow()
        if verification_code_entry:
            code = verification_code_entry.code
            expire_at_minutes = int(
                (verification_code_entry.expires_at - now).total_seconds() / 60
            )
        else:
            code = _generate_verification_code()
            verification_code_entry = await esm.generate_verification_token(
                user_id, email, virtual_lab_name, code, 1
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
        attempts = await rl.get_count(rd_key)
        remaining_attempts = settings.MAX_INIT_ATTEMPTS - (attempts or 0)

        return VliResponse.new(
            message="Verification code email sent successfully",
            data={
                "message": "Verification code email sent successfully",
                "status": VerificationCodeStatus.CODE_SENT.value,
                "remaining_time": None,
                "remaining_attempts": remaining_attempts,
            },
        )
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
