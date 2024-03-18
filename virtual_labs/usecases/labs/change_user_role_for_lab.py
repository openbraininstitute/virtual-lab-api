from http import HTTPStatus
from json import loads

from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import LabResponse, VirtualLabUser
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)
from virtual_labs.usecases.labs.lab_authorization import is_user_admin_of_lab


def change_user_role_for_lab(
    lab_id: UUID4,
    user_making_change_id: UUID4,
    user_id: UUID4,
    new_role: UserRoleEnum,
    db: Session,
) -> LabResponse[VirtualLabUser]:
    user_mutation_repo = UserMutationRepository()
    user_query_repo = UserQueryRepository()

    try:
        lab = lab_repository.get_virtual_lab(db, lab_id)
        if not is_user_admin_of_lab(user_id=user_making_change_id, lab=lab):
            raise VliError(
                message=f"Only admins of lab {lab.name} can change roles for other users",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.FORBIDDEN,
            )
        user = user_query_repo.retrieve_user_from_kc(str(user_id))

        new_group_id = (
            lab.admin_group_id
            if new_role.value == UserRoleEnum.admin.value
            else lab.member_group_id
        )

        if user_query_repo.is_user_in_group(user_id, str(new_group_id)):
            # User already has `new_role`. Nothing else to do
            return LabResponse[VirtualLabUser](
                message="User already has this role",
                data=VirtualLabUser(user=user),
            )

        old_group_id = (
            lab.member_group_id
            if new_role.value == UserRoleEnum.admin.value
            else lab.admin_group_id
        )

        user_mutation_repo.detach_user_from_group(
            user_id=user_id, group_id=str(old_group_id)
        )
        user_mutation_repo.attach_user_to_group(
            user_id=user_id, group_id=str(new_group_id)
        )

        return LabResponse[VirtualLabUser](
            message="Successfully changed user role", data=VirtualLabUser(user=user)
        )
    except SQLAlchemyError as error:
        logger.error(
            f"Db error when retrieving virtual lab {lab_id} for removing user {user_id}. {error}"
        )
        raise VliError(
            message="Virtual lab could not be retrieved",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    except IdentityError as error:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=error.message,
            details=error.detail,
        )
    # TODO: The Keycloak error shoulf be replaced by IdentityError
    except KeycloakError as error:
        logger.warning(
            f"Removing user {user_id} from lab {lab_id}, groups failed: {loads(error.error_message)["error"]}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
            message="Removing user from virtual lab failed due to a keycloak error",
        )
    except VliError as error:
        raise error
    except Exception as error:
        logger.warning(
            f"Unknown error when removing user {user_id} to lab {lab_id}: {error}"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding user to virtual lab failed due to an internal server error",
        )
