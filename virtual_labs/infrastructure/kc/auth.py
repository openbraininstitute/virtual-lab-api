from http import HTTPStatus as status
from typing import Tuple

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
)

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings

from .config import kc_auth

auth_header: HTTPBearer | OAuth2AuthorizationCodeBearer = HTTPBearer(auto_error=False)

if settings.PY_ENV == "dev":
    auth_header = OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{settings.KC_SERVER_URI}realms/{settings.KC_REALM_NAME}/protocol/openid-connect/auth",
        tokenUrl=f"{settings.KC_SERVER_URI}realms/{settings.KC_REALM_NAME}/protocol/openid-connect/token",
        auto_error=False,
    )


def get_public_key() -> str:
    """
    get the public key to decode the token
    """
    return (
        f"-----BEGIN PUBLIC KEY-----\n{kc_auth.public_key()}\n-----END PUBLIC KEY-----"
    )


def verify_jwt(
    header: HTTPAuthorizationCredentials = Depends(auth_header),
) -> Tuple[AuthUser, str]:
    if not header:
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=status.UNAUTHORIZED,
            message="Invalid authentication credentials",
            details="The supplied authentication is not authorized to access",
        )

    try:
        token = header.credentials
        decoded_token = kc_auth.decode_token(
            token=token,
            key=get_public_key(),
            options={
                "verify_aut": True,
                "verify_signature": True,
                "verify_exp": True,
            },
        )
    except Exception:
        raise VliError(
            error_code=VliErrorCode.AUTHORIZATION_ERROR,
            http_status_code=status.UNAUTHORIZED,
            message="Invalid authentication credentials",
        )
    try:
        user = AuthUser(**decoded_token)
        return (user, token)
    except Exception:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=status.BAD_REQUEST,
            message="Invalid authentication credentials",
            details="The user details is not correct",
        )
