from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from jwt import ExpiredSignatureError, PyJWTError
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.email.email_utils import (
    InviteOrigin,
    get_invite_details_from_token,
)
from virtual_labs.infrastructure.kc.models import AuthUser

from .accept_invite_by_id import accept_invite_by_id


async def accept_invite_by_token(
    session: AsyncSession,
    *,
    invite_token: str,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    try:
        decoded_token = get_invite_details_from_token(
            invite_token=invite_token,
        )
        invite_id = decoded_token.get("invite_id")
        origin = decoded_token.get("origin")

        return await accept_invite_by_id(
            session,
            invite_id=UUID(invite_id),
            invite_origin=InviteOrigin(origin),
            auth=auth,
        )

    except ExpiredSignatureError as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.TOKEN_EXPIRED,
            http_status_code=status.BAD_REQUEST,
            message="Invite Token is not valid",
            details="Invitation is expired",
        )
    except PyJWTError as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.INVALID_PARAMETER,
            http_status_code=status.BAD_REQUEST,
            message="Invite Token is not valid",
            details="Invitation token is malformed",
        )
