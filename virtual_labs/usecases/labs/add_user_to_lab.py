from http import HTTPStatus
from json import loads

from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import AddUser
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.user_repo import UserMutationRepository


def add_user_to_lab(lab_id: UUID4, user: AddUser, db: Session) -> AddUser:
    try:
        lab = lab_repository.get_virtual_lab(db, lab_id)
        user_repository = UserMutationRepository()

        group_id = (
            lab.admin_group_id
            if user.role.value == UserRoleEnum.admin.value
            else lab.member_group_id
        )

        user_repository.attach_user_to_group(
            user_id=user.user_id, group_id=str(group_id)
        )

        return user
    except SQLAlchemyError as error:
        logger.error(
            f"Db error when retrieving virtual lab {lab_id} for adding user {user.user_id}. {error}"
        )
        raise VliError(
            message="Virtual lab could not be retrieved",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except KeycloakError as error:
        logger.warning(
            f"Adding user {user.user_id} to lab {lab_id}, group {group_id} failed: {loads(error.error_message)["error"]}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Adding user to virtual lab failed due to a keycloak error",
        )
    except Exception as error:
        logger.warning(
            f"Unknown error when adding user {user.user_id} to lab {lab_id}, group {group_id}: {error}"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding user to virtual lab failed due to an internal server error",
        )
