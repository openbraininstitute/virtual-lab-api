"""
Admin authorization verification decorator.
Ensures that the authenticated user belongs to one of the specified groups in Keycloak.
"""

from functools import wraps
from http import HTTPStatus as status
from typing import Any, Callable, List, Tuple

from keycloak import KeycloakError  # type: ignore
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.config import kc_auth
from virtual_labs.infrastructure.kc.models import AuthUser


def verify_service_admin(allowed_groups: List[str]) -> Callable[..., Any]:
    """
    Decorator factory that verifies the authenticated user is a member of
    at least one of the specified Keycloak groups.

    Args:
        allowed_groups: List of Keycloak group paths the user must belong to
                        (at least one).

    Raises:
        VliError: If the user is not authorized (not in any allowed group)
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
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

                _, token = auth

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

                user_groups = user_info.get("groups", [])

                if not any(group in user_groups for group in allowed_groups):
                    logger.warning(
                        f"Unauthorized access attempt by user: {auth[0].sub}. "
                        f"User groups: {user_groups}, required one of: {allowed_groups}"
                    )
                    raise VliError(
                        error_code=VliErrorCode.AUTHORIZATION_ERROR,
                        http_status_code=status.FORBIDDEN,
                        message="Access denied",
                        details="You do not have the required privileges to access this resource",
                    )

                logger.info(f"Admin access granted for user: {auth[0].sub}")
                return await f(*args, **kwargs)

            except VliError:
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

    return decorator
