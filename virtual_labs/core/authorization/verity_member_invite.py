import asyncio
from functools import wraps
from http import HTTPStatus as status
from typing import Any, Callable

from keycloak import KeycloakError  # type: ignore
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.invite import AddUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.shared.utils.is_user_in_list import (
    is_user_in_list_soft,
)
from virtual_labs.shared.utils.uniq_list import uniq_list


async def authorize_user_for_member_invite(
    user_id: str,
    virtual_lab_id: UUID4,
    invite_details: AddUser,
    session: AsyncSession,
) -> None:
    gqr = GroupQueryRepository()
    vlab = await get_undeleted_virtual_lab(
        session,
        lab_id=virtual_lab_id,
    )
    admins, members = await asyncio.gather(
        gqr.a_retrieve_group_users(group_id=str(vlab.admin_group_id)),
        gqr.a_retrieve_group_users(group_id=str(vlab.member_group_id)),
    )
    uniq_admin_users = uniq_list([u.id for u in admins])
    uniq_member_users = uniq_list([u.id for u in members])

    if is_user_in_list_soft(list_=uniq_admin_users, user_id=user_id) or (
        is_user_in_list_soft(list_=uniq_member_users, user_id=user_id)
        and invite_details.role == UserRoleEnum.member
    ):
        pass
    else:
        raise UserNotInList("User not found in the list")


def verity_member_invite(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    This decorator to check if the user is allowed to invite another member
    allowed in this cases:
        1. user is in admin list
        2. user is a member and the invitee role is a member
    """

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            virtual_lab_id = kwargs["virtual_lab_id"]
            invite_details: AddUser = kwargs["invite_details"]
            session = kwargs["session"]
            auth = kwargs["auth"]
            user_id = get_user_id_from_auth(auth)

            await authorize_user_for_member_invite(
                user_id=str(user_id),
                virtual_lab_id=virtual_lab_id,
                invite_details=invite_details,
                session=session,
            )

        except NoResultFound:
            raise VliError(
                error_code=VliErrorCode.DATABASE_ERROR,
                http_status_code=status.NOT_FOUND,
                message="No virtual lab with this id found",
            )
        except SQLAlchemyError as e:
            logger.exception(f"SQL Error: {e}")
            raise VliError(
                error_code=VliErrorCode.DATABASE_ERROR,
                http_status_code=status.INTERNAL_SERVER_ERROR,
                message="This virtual lab could not be retrieved from the db",
            )
        except UserNotInList:
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="[verity_member_invite] The supplied authentication is not authorized for this action",
            )
        except KeycloakError as error:
            logger.error(
                f"Keycloak error MESSAGE: {error.response_code} {error.response_body} {error.error_message}"
            )
            logger.exception(f"Keycloak get error {error}")
            raise VliError(
                error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
                http_status_code=error.response_code or status.BAD_REQUEST,
                message="Checking for authorization failed",
                details=error.__str__,
            )
        except Exception as error:
            logger.exception(f"Error while checking authorization {error}")
            raise VliError(
                error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
                http_status_code=status.BAD_REQUEST,
                message="Checking for authorization failed",
            )

        else:
            return await f(*args, **kwargs)

    return wrapper
