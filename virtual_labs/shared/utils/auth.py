from typing import Dict
from uuid import UUID

from pydantic import UUID4, EmailStr

from virtual_labs.infrastructure.kc.models import AuthUser


def get_user_id_from_auth(auth: tuple[AuthUser, str]) -> UUID4:
    """Returns uuid of the test user created in keycloak."""
    return UUID(auth[0].sub)


def get_user_email_from_auth(auth: tuple[AuthUser, str]) -> EmailStr:
    """Returns email of the test user created in keycloak."""
    return auth[0].email


def get_user_metadata(auth_user: AuthUser) -> Dict[str, str]:
    """
    extract user metadata from AuthUser for use in Stripe.

    Args:
        auth_user: The authenticated user

    Returns:
        Dict[str, str]: A dictionary containing user metadata
    """
    return {
        "user_id": auth_user.sub,
        "username": auth_user.username,
        "email": auth_user.email,
        "full_name": auth_user.name if auth_user.name else "",
        "email_verified": str(auth_user.email_verified).lower(),
    }
