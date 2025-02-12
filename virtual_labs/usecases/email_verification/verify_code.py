from datetime import datetime, timedelta
from typing import Tuple

from fastapi.responses import Response
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.email_verification import (
    EmailValidationMutationRepository,
    EmailValidationQueryRepository,
)


class EmailVerificationException(Exception):
    """Base exception for email verification errors"""


class InvalidEmailError(EmailVerificationException):
    """Raised when email validation fails"""


class EmailAlreadyRegisteredError(EmailVerificationException):
    """Raised when email is already registered"""


CODE_LENGTH = 6
MAX_ATTEMPTS = 3
LOCK_TIME_MINUTES = 15


async def verify_code(
    session: AsyncSession,
    *,
    email: EmailStr,
    code: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    """Start email verification process"""
    es = EmailValidationQueryRepository(session)
    esm = EmailValidationMutationRepository(session)

    now = datetime.utcnow()
    # Check existing user
    verification = await es.get_verification_token(email)
    if not verification:
        raise EmailVerificationException("No active verification found")

    if verification.locked_until and verification.locked_until > now:
        remaining_time = (verification.locked_until - now).seconds // 60
        raise EmailVerificationException(
            f"Too many attempts. Try again in {remaining_time} minutes"
        )

    if verification.token != code.strip():
        verification.attempts += 1
        if verification.attempts >= MAX_ATTEMPTS:
            verification.locked_until = now + timedelta(minutes=LOCK_TIME_MINUTES)
        await session.commit()

        remaining_attempts = MAX_ATTEMPTS - verification.attempts
        if remaining_attempts > 0:
            raise EmailVerificationException(
                f"Invalid code. {remaining_attempts} attempts remaining"
            )
        raise EmailVerificationException(
            "Too many incorrect attempts. Code locked for 15 minutes"
        )

    verification.is_used = True
    await session.commit()
