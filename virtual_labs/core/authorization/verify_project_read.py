from functools import wraps
from http import HTTPStatus as status
from typing import Any, Callable

from keycloak import KeycloakError  # type:ignore
from loguru import logger
from sqlalchemy.exc import NoResultFound, SQLAlchemyError

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import UserNotInList
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.shared.utils.is_user_in_list import is_user_in_list
from virtual_labs.shared.utils.uniq_list import uniq_list


def verify_project_read(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    This decorator to check if the user user is either admin or member of project
    to perform this action
    """

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            project_id = kwargs["project_id"]
            session = kwargs["session"]
            auth = kwargs["auth"]
            user_id = get_user_id_from_auth(auth)

            gqr = GroupQueryRepository()
            pqr = ProjectQueryRepository(session)

            project, _ = await pqr.retrieve_one_project_by_id(project_id=project_id)
            admins = gqr.retrieve_group_users(group_id=str(project.admin_group_id))
            members = gqr.retrieve_group_users(group_id=str(project.member_group_id))
            users = admins + members

            uniq_users = uniq_list([u.id for u in users])
            is_user_in_list(list_=uniq_users, user_id=str(user_id))
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
                message="[verify_project_read] The supplied authentication is not authorized for this action",
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
            logger.exception(f"Unknown error when checking for project_read: {error}")
            raise VliError(
                error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
                http_status_code=status.BAD_REQUEST,
                message="Checking for authorization failed",
            )

        else:
            return await f(*args, **kwargs)

    return wrapper
