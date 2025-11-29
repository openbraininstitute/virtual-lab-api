from typing import Dict, Tuple

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.labs import UserStats
from virtual_labs.domain.user import (
    OnboardingFeature,
    OnboardingStatus,
    OnboardingUpdateRequest,
    SetRecentWorkspaceRequest,
    UpdateUserProfileRequest,
    UserGroupsResponse,
    UserProfileResponse,
)
from virtual_labs.domain.workspace import RecentWorkspaceResponseWithDetails
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases.labs.get_user_stats import get_user_stats
from virtual_labs.usecases.users import (
    get_user_onboarding_status,
    get_user_profile,
    reset_all_user_onboarding_status,
    reset_user_onboarding_status,
    set_recent_workspace,
    update_user_onboarding_status,
    update_user_profile,
)
from virtual_labs.usecases.users.get_all_user_groups import get_all_user_groups
from virtual_labs.usecases.users.get_recent_workspace import get_recent_workspace

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


@router.get(
    "/preferences/recent-workspace",
    summary="Get recent workspace",
    description="Get the user's most recently visited workspace (virtual lab + project combination)",
    response_model=VliAppResponse[RecentWorkspaceResponseWithDetails],
    response_model_exclude_none=False,
)
async def get_recent_workspace_endpoint(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Get the user's recent workspace. If no preference exists, returns the default workspace
    (last created project in user's virtual lab).

    Returns:
        Response: Recent workspace information
    """
    return await get_recent_workspace(auth=auth, session=session)


@router.post(
    "/preferences/recent-workspace",
    summary="Set recent workspace",
    description="Set the user's most recently visited workspace (virtual lab + project combination)",
    response_model=VliAppResponse[RecentWorkspaceResponseWithDetails],
    response_model_exclude_none=False,
)
async def set_recent_workspace_endpoint(
    payload: SetRecentWorkspaceRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Set the user's recent workspace after validating access permissions.

    Args:
        payload: The workspace information to set

    Returns:
        Response: Confirmation of workspace update
    """
    return await set_recent_workspace(
        request=payload,
        auth=auth,
        session=session,
    )


@router.get(
    "/preferences/onboarding",
    summary="Get onboarding status",
    description="Get the user's onboarding status for all features",
    response_model=VliAppResponse[Dict[str, OnboardingStatus]],
)
async def get_onboarding_status_endpoint(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Get the user's onboarding status.

    Returns:
        Response: Onboarding status dictionary
    """
    return await get_user_onboarding_status(
        auth=auth,
        session=session,
    )


@router.put(
    "/preferences/onboarding/{feature}",
    summary="Update onboarding status",
    description="Update the onboarding status for a specific feature",
    response_model=VliAppResponse[Dict[str, OnboardingStatus]],
)
async def update_onboarding_status_endpoint(
    feature: OnboardingFeature,
    payload: OnboardingUpdateRequest,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Update the onboarding status for a specific feature.

    Args:
        feature: The feature identifier
        payload: The status update

    Returns:
        Response: Updated feature status
    """
    return await update_user_onboarding_status(
        feature=feature.value,
        payload=payload,
        auth=auth,
        session=session,
    )


@router.delete(
    "/preferences/onboarding/{feature}",
    summary="Reset onboarding status",
    description="Reset the onboarding status for a specific feature",
    response_model=VliAppResponse[Dict[str, OnboardingStatus]],
)
async def reset_onboarding_status_endpoint(
    feature: OnboardingFeature,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Reset the onboarding status for a specific feature.

    Args:
        feature: The feature identifier

    Returns:
        Response: Status of the reset operation
    """
    return await reset_user_onboarding_status(
        feature=feature.value,
        auth=auth,
        session=session,
    )


@router.delete(
    "/preferences/onboarding",
    summary="Reset all onboarding status",
    description="Reset the onboarding status for all features",
    response_model=VliAppResponse[Dict[str, OnboardingStatus]],
)
async def reset_all_onboarding_status_endpoint(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    """
    Reset the onboarding status for all features.

    Returns:
        Response: Status of the reset operation
    """
    return await reset_all_user_onboarding_status(
        auth=auth,
        session=session,
    )
