from typing import Tuple

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.invite import InvitationResponse, InviteOut
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import invites as invite_cases

router = APIRouter(
    prefix="/invites",
    tags=["Invites"],
)


@router.get(
    "",
    operation_id="get_invite_details",
    summary="Retrieve invite details by token",
    response_model=VliAppResponse[InvitationResponse],
)
async def get_invite_details(
    session: AsyncSession = Depends(default_session_factory),
    token: str = Query("", description="invitation token"),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await invite_cases.get_invite_details(
        session,
        invite_token=token,
        auth=auth,
    )


@router.post(
    "",
    operation_id="invite_handler",
    summary="This will process the invite (add users to groups, update the invite status)",
    response_model=VliAppResponse[InviteOut],
)
async def handle_invite(
    session: AsyncSession = Depends(default_session_factory),
    token: str = Query("", description="invitation token"),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await invite_cases.invitation_handler(
        session,
        invite_token=token,
        auth=auth,
    )
