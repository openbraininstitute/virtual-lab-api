from http import HTTPStatus
from json import loads
from uuid import UUID

from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.repositories import labs as lab_repo
from virtual_labs.repositories.invite_repo import InviteMutationRepository
from virtual_labs.repositories.user_repo import UserMutationRepository


def accept_invite(invite_id: UUID4, user_id: UUID4, db: Session) -> None:
    """Called by the invited member when they click on the "accept invite" link.
    This function does the following:

    1. Adds user to the appropriate group (admin/member) in the virtual lab
    2. Updates the invite row to indicate that the invite has been accepted at time now()
    """

    try:
        invite_repo = InviteMutationRepository(db)
        user_repo = UserMutationRepository()

        invite = invite_repo.get_invite(invite_id)
        lab = lab_repo.get_virtual_lab(db, lab_id=UUID(str(invite.virtual_lab_id)))
        role = invite.role

        group_id = (
            lab.admin_group_id
            if role == UserRoleEnum.admin.value
            else lab.member_group_id
        )
        user_repo.attach_user_to_group(
            user_id=UUID(str(user_id)), group_id=str(group_id)
        )
        invite_repo.update_invite(invite_id=invite_id, accepted=True)
    except SQLAlchemyError as error:  # noqa: F821
        logger.error(f"Invitation acceptance failed due to db error: {error}")
        raise VliError(
            message=f"Invitation acceptance failed due to db error: {error}",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except KeycloakError as error:
        logger.warning(
            f"Adding user {user_id} to lab {lab.id}, group {group_id} failed: {loads(error.error_message)["error"]}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Adding user to virtual lab failed due to a keycloak error",
        )
    except Exception as error:
        logger.warning(
            f"Unknown error when adding user {user_id} to lab {lab.id}, group {group_id}: {error}"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding user to virtual lab failed due to an internal server error",
        )
