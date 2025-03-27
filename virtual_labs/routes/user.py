from typing import Tuple

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.labs import UserStats
from virtual_labs.domain.user import (
    UpdateUserProfileRequest,
    UserGroupsResponse,
    UserProfileResponse,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases.labs.get_user_stats import get_user_stats
from virtual_labs.usecases.users import (
    get_all_user_groups,
    get_user_profile,
    update_user_profile,
)

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
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    update the profile information for the authenticated user.

    Args:
        payload: The user profile data to update

    Returns:
        Response: the updated user profile information
    """
    return await update_user_profile(
        payload=payload,
        auth=auth,
        session=session,
    )


@router.get(
    "/groups",
    summary="Get all user groups",
    description="Get all groups the authenticated user is a part of (admin or member) for all virtual labs and projects",
    response_model=VliAppResponse[UserGroupsResponse],
)
async def get_all_user_groups_endpoint(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Get all groups the authenticated user is a part of.

    Returns:
        Response: List of all user groups across virtual labs and projects
    """
    return await get_all_user_groups(session=session, auth=auth)


@router.get(
    "/stats",
    summary="Get user statistics",
    description="Get comprehensive statistics for the authenticated user including virtual labs, pending invites, and projects",
    response_model=VliAppResponse[UserStats],
)
async def get_user_statistics(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """Get comprehensive statistics for the authenticated user"""
    return await get_user_stats(session, auth)
