from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from jwt import ExpiredSignatureError, PyJWTError
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.invite import InvitationResponse
from virtual_labs.infrastructure.db.models import ProjectInvite, VirtualLabInvite
from virtual_labs.infrastructure.email.email_utils import (
    InviteOrigin,
    get_invite_details_from_token,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.invite_repo import (
    InviteQueryRepository,
)
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import (
    UserQueryRepository,
)


async def get_invite_details(
    session: AsyncSession,
    *,
    invite_token: str,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    iqr = InviteQueryRepository(session)
    uqr = UserQueryRepository()
    pqr = ProjectQueryRepository(session)
    try:
        decoded_token = get_invite_details_from_token(
            invite_token=invite_token,
        )
        invite_id = decoded_token.get("invite_id")
        origin = decoded_token.get("origin")

        invite: VirtualLabInvite | ProjectInvite | None = None
        virtual_lab = None
        project = None

        if origin == InviteOrigin.LAB.value:
            invite = await iqr.get_vlab_invite_by_id(invite_id=UUID(invite_id))
            virtual_lab = await get_undeleted_virtual_lab(
                db=session,
                lab_id=UUID(str(invite.virtual_lab_id)),
            )
        elif origin == InviteOrigin.PROJECT.value:
            invite = await iqr.get_project_invite_by_id(invite_id=UUID(invite_id))
            project, virtual_lab = await pqr.retrieve_one_project_by_id(
                project_id=invite.project_id
            )
        else:
            raise ValueError(f"Origin {origin} is not allowed.")

        inviter = await uqr.a_retrieve_user_from_kc(
            str(invite.inviter_id),
        )

        assert inviter is not None

        inviter_full_name = (
            f"{inviter.firstName} {inviter.lastName}"
            if inviter.firstName and inviter.lastName
            else inviter.username
        )

        return VliResponse[InvitationResponse].new(
            message=f"Invite for {origin} received successfully",
            data=InvitationResponse.model_validate(
                {
                    "origin": origin,
                    "accepted": invite.accepted,
                    "invite_id": invite_id,
                    "inviter_full_name": inviter_full_name,
                    "virtual_lab_id": virtual_lab.id,
                    "virtual_lab_name": virtual_lab.name,
                    "project_id": project.id if project else None,
                    "project_name": project.name if project else None,
                }
            ),
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
    except SQLAlchemyError:
        logger.error(
            "Invite {} not found for origin {}".format(
                decoded_token.get("invite_id", None), decoded_token.get("origin")
            )
        )
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.NOT_FOUND,
            message="No invite was found for this link",
            details="The invite link is either malformed or the invite is deleted",
        )
    except (ValueError, AssertionError) as ex:
        logger.error(f"Could not retrieve users from keycloak: ({ex})")
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.BAD_REQUEST,
            message=str(ex),
        )
    except IdentityError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_GATEWAY,
            message="Could not attach user to group",
        )
    except Exception as ex:
        logger.exception(f"Error during processing the invitation: ({ex})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=status.INTERNAL_SERVER_ERROR,
            message="Processing invitation failed",
            details=str(ex),
        )
