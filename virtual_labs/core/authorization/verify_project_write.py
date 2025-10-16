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
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.shared.utils.is_user_in_list import is_user_in_list
from virtual_labs.shared.utils.uniq_list import uniq_list


async def authorize_user_for_project_write(
    user_id: str,
    project_id: UUID4,
    session: AsyncSession,
) -> bool:
    gqr = GroupQueryRepository()
    pqr = ProjectQueryRepository(session)

    project, _ = await pqr.retrieve_one_project_by_id(project_id=project_id)
    users = await gqr.a_retrieve_group_users(group_id=str(project.admin_group_id))
    uniq_users = uniq_list([u.id for u in users])

    return is_user_in_list(
        list_=uniq_users,
        user_id=user_id,
    )


def verify_project_write(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    This decorator to check if the user is project admin group
    to perform this action
    """

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            project_id = kwargs["project_id"]
            session = kwargs["session"]
            auth = kwargs["auth"]
            user_id = get_user_id_from_auth(auth)

            await authorize_user_for_project_write(
                user_id=str(user_id),
                project_id=project_id,
                session=session,
            )

        except NoResultFound:
            raise VliError(
                error_code=VliErrorCode.DATABASE_ERROR,
                http_status_code=status.NOT_FOUND,
                message="No project with this id found",
            )
        except SQLAlchemyError as e:
            logger.exception(f"SQL Error: {e}")
            raise VliError(
                error_code=VliErrorCode.DATABASE_ERROR,
                http_status_code=status.INTERNAL_SERVER_ERROR,
                message="This project could not be retrieved from the db",
            )
        except UserNotInList:
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="[verify_project_write] The supplied authentication is not authorized for this action",
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
            logger.exception(f"Unknown error when checking for project_write: {error}")
            raise VliError(
                error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
                http_status_code=status.BAD_REQUEST,
                message="Checking for authorization failed",
            )

        else:
            return await f(*args, **kwargs)

    return wrapper
