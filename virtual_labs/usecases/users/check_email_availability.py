from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def check_email_availability(
    email: str,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    Check whether the given email can be used for a profile update.

    Returns
        - 204 if the email is available,
    Raises
        - 422 if already taken by another user.
    """
    try:
        user_id = str(get_user_id_from_auth(auth))
        user_repo = UserQueryRepository()

        users = await user_repo.Kc.a_get_users({"email": email, "exact": "true"})

        is_taken = False
        if isinstance(users, list) and len(users) > 0:
            # if the only match is the caller themselves, the email is still available
            is_taken = not all(u.get("id") == user_id for u in users)

        if is_taken:
            raise VliError(
                error_code=VliErrorCode.INVALID_REQUEST,
                http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                message="This email address is not available. Please try another one.",
            )

        return Response(status_code=HTTPStatus.NO_CONTENT)
    except VliError:
        raise
    except Exception as e:
        logger.exception(f"Error checking email availability: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while checking email availability",
        )
