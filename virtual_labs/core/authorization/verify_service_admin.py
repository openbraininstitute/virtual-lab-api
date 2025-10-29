"""
Admin authorization verification decorator.
Ensures that the authenticated user belongs to the admin group in Keycloak.
"""

from functools import wraps
from http import HTTPStatus as status
from typing import Any, Callable, Tuple

from keycloak import KeycloakError  # type: ignore
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.kc.models import AuthUser

ADMIN_GROUP_PATH: str = "/service/virtual-lab-svc/admin"


def verify_service_admin(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that verifies the authenticated user is a member of the admin group.

    This decorator checks that the user making the request belongs to the
    Keycloak group "/service/virtual-lab-svc/admin".

    Raises:
        VliError: If the user is not authorized (not in admin group)
    """

    @wraps(f)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            auth: Tuple[AuthUser, str] | None = kwargs.get("auth")
            if not auth:
                raise VliError(
                    error_code=VliErrorCode.AUTHORIZATION_ERROR,
                    http_status_code=status.UNAUTHORIZED,
                    message="No authentication provided",
                    details="Authentication is required for admin endpoints",
                )

            # Extract token from auth tuple
            _, token = auth

            # Get user info including groups from Keycloak
            try:
                user_info = kc_auth.userinfo(token=token)
            except KeycloakError as kc_error:
                logger.error(
                    f"Keycloak error while fetching user info: CODE: {kc_error.response_code} "
                    f"BODY: {kc_error.response_body} MESSAGE: {kc_error.error_message}"
                )
                raise VliError(
                    error_code=VliErrorCode.AUTHORIZATION_ERROR,
                    http_status_code=kc_error.response_code or status.UNAUTHORIZED,
                    message="Failed to verify admin authorization",
                    details="Could not retrieve user information from identity provider",
                ) from kc_error

            # Check if user belongs to admin group
            user_groups = user_info.get("groups", [])

            if ADMIN_GROUP_PATH not in user_groups:
                logger.warning(
                    f"Unauthorized admin access attempt by user: {auth[0].sub}. "
                    f"User groups: {user_groups}"
                )
                raise VliError(
                    error_code=VliErrorCode.AUTHORIZATION_ERROR,
                    http_status_code=status.FORBIDDEN,
                    message="Access denied",
                    details="You do not have administrative privileges to access this resource",
                )

            logger.info(f"Admin access granted for user: {auth[0].sub}")
            return await f(*args, **kwargs)

        except VliError:
            # Re-raise VliError as-is
            raise
        except Exception as error:
            logger.exception(
                f"Unknown error when checking for admin authorization: {error}"
            )
            raise VliError(
                error_code=VliErrorCode.AUTHORIZATION_ERROR,
                http_status_code=status.FORBIDDEN,
                message="Admin authorization check failed",
                details=str(error),
            ) from error

    return wrapper
