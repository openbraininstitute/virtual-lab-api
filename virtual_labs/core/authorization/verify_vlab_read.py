from http import HTTPStatus as status
from typing import TypedDict

from fastapi import Depends
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_user_authenticated import (
    verify_user_authenticated,
)
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.labs import get_undeleted_virtual_lab
from virtual_labs.shared.utils.is_user_in_lab import is_user_in_lab


class AuthorizedVlabReadParams(TypedDict):
    user_id: UUID4
    virtual_lab: VirtualLab
    session: AsyncSession


async def verify_vlab_read(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    user_id: UUID4 = Depends(verify_user_authenticated),
) -> AuthorizedVlabReadParams:
    """
    Dependency to check if the user is authenticated and is authorized to read the virtual lab.
    """
    try:
        vlab = await get_undeleted_virtual_lab(
            session,
            lab_id=virtual_lab_id,
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
    try:
        if not (await is_user_in_lab(user_id, vlab)):
            raise VliError(
                error_code=VliErrorCode.NOT_ALLOWED_OP,
                http_status_code=status.FORBIDDEN,
                message="The supplied authentication is not authorized for this action",
            )
    except IdentityError:
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=status.UNAUTHORIZED,
            message="User is not authenticated to retrieve virtual labs",
        )
    except Exception as error:
        logger.exception(f" : {error}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=status.BAD_REQUEST,
            message="Checking for authorization failed",
        )
    return {"virtual_lab": vlab, "session": session, "user_id": user_id}
