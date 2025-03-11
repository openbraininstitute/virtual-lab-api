from http import HTTPStatus
from typing import Any, Dict, Tuple

from fastapi import Response
from loguru import logger

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import EntityNotFound
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import (
    UpdateUserProfileRequest,
    UserProfile,
    UserProfileResponse,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def update_user_profile(
    payload: UpdateUserProfileRequest,
    auth: Tuple[AuthUser, str],
) -> Response:
    """
    update the profile information for the authenticated user.

    Args:
        payload: The user profile data to update
        auth: auth tuple

    Returns:
        Response: updated user profile information
    """
    try:
        _, token = auth
        user_id = get_user_id_from_auth(auth)
        user_query_repo = UserQueryRepository()
        user_mutation_repo = UserMutationRepository()

        kc_user = await user_query_repo.get_user_info(token=token)

        if not kc_user:
            raise EntityNotFound

        # Update user attributes in Keycloak
        update_data: Dict[str, Any] = {}
        if payload.first_name is not None:
            update_data["firstName"] = payload.first_name
        if payload.last_name is not None:
            update_data["lastName"] = payload.last_name
        if payload.last_name is not None:
            update_data["email"] = kc_user["email"]

        attributes: Dict[str, Any] = getattr(kc_user, "attributes", {}) or {}

        updated_attributes: Dict[str, list[str]] = {}

        if payload.address is not None:
            updated_attributes["address"] = [payload.address]
        if payload.postal_code is not None:
            updated_attributes["postal_code"] = [payload.postal_code]
        if payload.city is not None:
            updated_attributes["city"] = [payload.city]
        if payload.state is not None:
            updated_attributes["state"] = [payload.state]
        if payload.country is not None:
            updated_attributes["country"] = [payload.country]

        if updated_attributes:
            merged_attributes: Dict[str, list[str]] = {}
            for key, value in attributes.items():
                if isinstance(value, list):
                    merged_attributes[key] = value
                else:
                    merged_attributes[key] = [str(value)]

            # Add updated attributes
            for key, value in updated_attributes.items():
                merged_attributes[key] = value

            update_data["attributes"] = merged_attributes

        if update_data:
            user_mutation_repo.Kc.update_user(user_id=str(user_id), payload=update_data)

            kc_user = await user_query_repo.get_user_info(token=token)

        updated_attrs: Dict[str, Any] = getattr(kc_user, "attributes", {}) or {}

        user_profile = UserProfile(
            id=user_id,
            preferred_username=kc_user["preferred_username"],
            email=kc_user["email"],
            first_name=kc_user["given_name"] or "",
            last_name=kc_user["family_name"] or "",
            email_verified=kc_user["email_verified"],
            address=updated_attrs.get("address", [None])[0]
            if "address" in updated_attrs
            else None,
            postal_code=updated_attrs.get("postal_code", [None])[0]
            if "postal_code" in updated_attrs
            else None,
            city=updated_attrs.get("city", [None])[0]
            if "city" in updated_attrs
            else None,
            state=updated_attrs.get("state", [None])[0]
            if "state" in updated_attrs
            else None,
            country=updated_attrs.get("country", [None])[0]
            if "country" in updated_attrs
            else None,
        )

        return VliResponse.new(
            message="User profile updated successfully",
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
        logger.exception(f"Error updating user profile: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while updating the user profile",
        )
