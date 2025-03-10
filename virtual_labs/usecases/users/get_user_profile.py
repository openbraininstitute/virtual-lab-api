from http import HTTPStatus
from typing import Any, Dict, Tuple

from fastapi import Response
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import EntityNotFound
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import UserProfile, UserProfileResponse
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_user_profile(
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    get the profile information for the authenticated user.

    Args:
        auth: auth tuple

    Returns:
        Response: the user profile information
    """
    try:
        _, token = auth
        user_id = get_user_id_from_auth(auth)
        user_repo = UserQueryRepository()

        kc_user = await user_repo.get_user_info(token=token)

        print("ᦨ #  get_user_profile.py:35 #  kc_user:", kc_user)

        if not kc_user:
            raise EntityNotFound

        attributes: Dict[str, Any] = getattr(kc_user, "attributes", {}) or {}

        user_profile = UserProfile(
            id=user_id,
            preferred_username=kc_user["preferred_username"],
            email=kc_user["email"] or "",
            first_name=kc_user["given_name"] or "",
            last_name=kc_user["family_name"] or "",
            email_verified=kc_user["email_verified"],
            address=attributes.get("address", [None])[0]
            if "address" in attributes
            else None,
            postal_code=attributes.get("postal_code", [None])[0]
            if "postal_code" in attributes
            else None,
            city=attributes.get("city", [None])[0] if "city" in attributes else None,
            state=attributes.get("state", [None])[0] if "state" in attributes else None,
            country=attributes.get("country", [None])[0]
            if "country" in attributes
            else None,
        )

        return VliResponse.new(
            message="User profile retrieved successfully",
            data=UserProfileResponse(profile=user_profile).model_dump(),
        )
    except EntityNotFound as e:
        logger.error(f"User not found: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="User not found",
        )
    except Exception as e:
        logger.exception(f"Error retrieving user profile: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while retrieving the user profile",
        )
