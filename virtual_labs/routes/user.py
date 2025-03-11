from typing import Tuple

from fastapi import APIRouter, Depends, Response

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.user import UpdateUserProfileRequest, UserProfileResponse
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases.users import get_user_profile, update_user_profile

router = APIRouter(
    prefix="/users",
    tags=["Users Endpoint"],
)


@router.get(
    "/profile",
    summary="Get user profile",
    description="Retrieve the profile information for the authenticated user",
    response_model=VliAppResponse[UserProfileResponse],
    response_model_exclude_none=False,
)
async def get_profile_endpoint(
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    get the profile information for the authenticated user.

    Returns:
        Response: the user profile information
    """
    return await get_user_profile(auth=auth)


@router.patch(
    "/profile",
    summary="Update user profile",
    description="Update the profile information for the authenticated user",
    response_model=VliAppResponse[UserProfileResponse],
    response_model_exclude_none=False,
)
async def update_profile_endpoint(
    payload: UpdateUserProfileRequest,
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    update the profile information for the authenticated user.

    Args:
        payload: The user profile data to update

    Returns:
        Response: the updated user profile information
    """
    return await update_user_profile(payload=payload, auth=auth)
