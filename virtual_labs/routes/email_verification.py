from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.email import Email, EmailVerificationPayload
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import email_verification as email_verification_usecases

router = APIRouter(prefix="/email", tags=["Email Verification Endpoints"])


@router.post(
    "/initiate-verification",
    operation_id="initiate_email_verification",
    summary="initiate email verification",
    response_model=VliAppResponse[None],
)
async def initiate_email_verification(
    email: Email,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
):
    email_verification_usecases.initiate_verification(
        session=session,
        email=email,
    )
    return {"message": "Verification email sent"}


@router.get(
    "/verify-code",
    operation_id="verify_code_email_verification",
    summary="finish email verification",
    response_model=VliAppResponse[None],
)
async def complete_email_verification(
    payload: EmailVerificationPayload,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
):
    email_verification_usecases.verify_code(
        session=session,
        email=payload.email,
        code=payload.code,
    )
    return {"message": "Verification email sent"}
