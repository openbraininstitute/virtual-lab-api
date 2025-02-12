import secrets
from http import HTTPStatus as status
from typing import Tuple

from fastapi.responses import Response
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.email import VerificationCode
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


def _generate_verification_code() -> VerificationCode:
    """Generate secure 6-digit numeric code"""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def initiate_verification(
    session: AsyncSession,
    *,
    email: EmailStr,
    auth: Tuple[AuthUser, str],
) -> Response:
    """Start email verification process"""
    es = EmailValidationQueryRepository(session)
    esm = EmailValidationMutationRepository(session)

    # Check existing user
    if await es.check_email_exists(email):
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=status.BAD_REQUEST,
            message="Email already registered",
        )

    # Invalidate previous tokens
    await esm.invalidate_previous_tokens(email)
    await esm.generate_verification_token(email, _generate_verification_code(), 1)

    # TODO: send email
    # self._send_verification_email(normalized_email, code)
