import asyncio
from http import HTTPStatus
from json import loads
from uuid import UUID

from keycloak import KeycloakError
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.labs import LabResponse, VirtualLabUser
from virtual_labs.domain.user import UserWithInviteStatus
from virtual_labs.repositories import labs as lab_repository
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)
from virtual_labs.shared.utils.is_user_in_lab import is_user_in_lab


async def change_user_role_for_lab(
    lab_id: UUID4,
    user_id: UUID4,
    new_role: UserRoleEnum,
    db: AsyncSession,
) -> LabResponse[VirtualLabUser]:
    umr = UserMutationRepository()
    uqr = UserQueryRepository()
    gqr = GroupQueryRepository()

    try:
        virtual_lab = await lab_repository.get_undeleted_virtual_lab(db, lab_id)
        user = await uqr.a_retrieve_user_from_kc(user_id)

        if virtual_lab.owner_id == user_id:
            raise VliError(
                message="Cannot change role of owner of the virtual lab",
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        if not is_user_in_lab(UUID(user.id), virtual_lab):
            raise VliError(
                message="Cannot change role of user that does not belong in lab",
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        admins = await gqr.a_retrieve_group_users(
            str(virtual_lab.admin_group_id),
        )

        if (
            len(admins) == 1
            and admins[0].id == str(user_id)
            and new_role == UserRoleEnum.member
        ):
            raise VliError(
                message=f"Last admin of lab {lab_id} cannot be converted to member",
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                details="Lab needs to have at least 1 admin.",
            )

        attach_group_id, detach_group_id = (
            (virtual_lab.admin_group_id, virtual_lab.member_group_id)
            if new_role.value == UserRoleEnum.admin.value
            else (virtual_lab.member_group_id, virtual_lab.admin_group_id)
        )

        if uqr.is_user_in_group(user_id, str(attach_group_id)):
            # User already has `new_role`. Nothing else to do
            return LabResponse[VirtualLabUser](
                message="User already has this role",
                data=VirtualLabUser(
                    user=UserWithInviteStatus(
                        **user.model_dump(), invite_accepted=True, role=new_role
                    )
                ),
            )

        await asyncio.gather(
            umr.a_detach_user_from_group(
                user_id=user_id,
                group_id=str(detach_group_id),
            ),
            umr.a_attach_user_to_group(
                user_id=user_id,
                group_id=str(attach_group_id),
            ),
        )

        return LabResponse[VirtualLabUser](
            message="Successfully changed user role",
            data=VirtualLabUser(
                user=UserWithInviteStatus(
                    **user.model_dump(), invite_accepted=True, role=new_role
                )
            ),
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
    # TODO: The Keycloak error should be replaced by IdentityError
    except KeycloakError as error:
        logger.warning(
            f"Removing user {user_id} from lab {lab_id}, groups failed: {loads(error.error_message)['error']}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=error.response_code or HTTPStatus.BAD_GATEWAY,
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
