from typing import Annotated, Tuple

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.invite import (
    InvitationResponse,
    InviteOut,
    WebhookHeaders,
    WebhookPayload,
)
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


@router.post(
    "/webhook",
    operation_id="invites_webhook_handler",
    summary="Handle incoming webhook to invite a user to a project",
    description="This is tied to the google form invite setup",
)
async def webhook_handler(
    request: Request,
    x_webhook_signature: Annotated[str, Header()],
    x_virtual_lab_id: Annotated[str, Header()],
    x_project_id: Annotated[str, Header()],
    x_user_id: Annotated[str, Header()],
    session: AsyncSession = Depends(default_session_factory),
) -> JSONResponse:
    try:
        headers = WebhookHeaders(
            x_webhook_signature=x_webhook_signature,
            x_virtual_lab_id=x_virtual_lab_id,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            x_project_id=x_project_id,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            x_user_id=x_user_id,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
        )
    except ValidationError as e:
        return JSONResponse(status_code=422, content={"detail": e.errors()})

    body = await request.body()

    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError as e:
        return JSONResponse(status_code=422, content={"detail": e.errors()})

    result = await invite_cases.handle_invite_webhook(
        session,
        signature=headers.x_webhook_signature,
        body=body,
        virtual_lab_id=str(headers.x_virtual_lab_id),
        project_id=str(headers.x_project_id),
        inviter_id=str(headers.x_user_id),
        invitee_email=payload.email,
        invitee_name=payload.name,
    )
    return JSONResponse(status_code=200, content=result)
