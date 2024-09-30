from http import HTTPStatus as status
from uuid import UUID

from fastapi import Depends
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.auth import auth_user_id
from virtual_labs.repositories.user_repo import UserQueryRepository


async def verify_user_authenticated(
    user_id: str = Depends(auth_user_id),
) -> UUID:
    """
    This dependency checks that the request contains auth headers with a bearer token that
    corresponds to a valid keycloak user (i.e. the user making the request is recognized by our identity provider)
    """
    user_repo = UserQueryRepository()
    try:
        user = await user_repo.retrieve_user_from_kc(user_id)
        return UUID(user.id)
    except Exception as error:
        logger.exception(
            f"Unknown error when checking for user_authentication: {error}"
        )
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=status.UNAUTHORIZED,
            message="Checking for authorization failed",
            details=str(error),
        )
