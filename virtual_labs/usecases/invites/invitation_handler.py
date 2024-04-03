from http import HTTPStatus as status
from typing import Tuple
from uuid import UUID

from fastapi import Response
from jwt import ExpiredSignatureError
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError, UserMismatch
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.infrastructure.email.email_utils import (
    InviteOrigin,
    get_invite_details_from_token,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.invite_repo import (
    InviteMutationRepository,
    InviteQueryRepository,
)
from virtual_labs.repositories.labs import get_virtual_lab
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)


async def invitation_handler(
    session: Session,
    *,
    invite_token: str,
    auth: Tuple[AuthUser, str],
) -> Response | VliError:
    project_query_repo = ProjectQueryRepository(session)
    invite_mut_repo = InviteMutationRepository(session)
    invite_query_repo = InviteQueryRepository(session)
    user_mut_repo = UserMutationRepository()
    user_query_repo = UserQueryRepository()

    try:
        decoded_token = get_invite_details_from_token(
            invite_token=invite_token,
        )
        invite_id = decoded_token.get("invite_id")
        origin = decoded_token.get("origin")

        if origin == InviteOrigin.LAB.value:
            vlab_invite = invite_query_repo.get_vlab_invite_by_id(invite_id=invite_id)
            if vlab_invite.user_email != auth[0].email:
                raise UserMismatch

            vlab = get_virtual_lab(
                db=session,
                lab_id=UUID(str(vlab_invite.virtual_lab_id)),
            )
            user = user_query_repo.retrieve_user_by_email(
                email=vlab_invite.user_email,
            )

            group_id = (
                vlab.admin_group_id
                if vlab_invite.role == UserRoleEnum.admin.value
                else vlab.member_group_id
            )
            user_mut_repo.attach_user_to_group(
                user_id=user.id,
                group_id=str(group_id),
            )

            invite_mut_repo.update_vlab_invite(
                invite_id=UUID(str(vlab_invite.id)),
                accepted=True,
            )
        elif origin == InviteOrigin.PROJECT.value:
            project_invite = invite_query_repo.get_project_invite_by_id(
                invite_id=invite_id
            )
            if project_invite.user_email != auth[0].email:
                raise UserMismatch
            user = user_query_repo.retrieve_user_by_email(
                email=project_invite.user_email
            )
            project, _ = project_query_repo.retrieve_one_project_by_id(
                project_id=UUID(str(project_invite.project_id))
            )
            group_id = (
                project.admin_group_id
                if project_invite.role == UserRoleEnum.admin.value
                else project.member_group_id
            )
            user_mut_repo.attach_user_to_group(
                user_id=user.id,
                group_id=str(group_id),
            )
            invite_mut_repo.update_project_invite(
                invite_id=UUID(str(project_invite.id)),
                properties={"accepted": True, "updated_at": func.now()},
            )
        else:
            raise ValueError(f"Origin {origin} is allowed.")
    except ExpiredSignatureError as ex:
        logger.error(f"Error during processing the invite: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Invite Token is not valid",
        )
    except ValueError as ex:
        logger.error(f"Could not retrieve users from keycloak: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message=str(ex),
        )
    except IdentityError:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Could not attach user to group",
        )
    except Exception as ex:
        logger.error(f"Error during creating/attaching to group in KC: ({ex})")
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="KC Group creation/attaching failed",
        )
