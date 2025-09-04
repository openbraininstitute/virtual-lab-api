import asyncio
from http import HTTPStatus
from typing import Optional, Tuple

from fastapi import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import ProjectVlOut
from virtual_labs.domain.user import Workspace
from virtual_labs.domain.workspace import (
    RecentWorkspaceOutWithDetails,
    RecentWorkspaceResponseWithDetails,
)
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_preference_repo import UserPreferenceQueryRepository
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def get_recent_workspace(
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    """
    Get the user's recent workspace. If no preference exists, find the default workspace
    which is the last created project in the user's virtual lab (each user owns one VL).

    Args:
        auth: Authentication tuple
        session: Database session

    Returns:
        Response: Recent workspace information
    """
    try:
        user_id = get_user_id_from_auth(auth)
        preference_repo = UserPreferenceQueryRepository(session)
        group_repo = GroupQueryRepository()

        # Get user's preference
        preference = await preference_repo.get_user_preference(user_id)
        recent_workspace_data = await preference_repo.get_user_recent_workspace(user_id)

        workspace = None
        updated_at = None
        if recent_workspace_data:
            # Validate that user still has access to this workspace
            workspace = await _validate_workspace_access(
                session,
                user_id,
                recent_workspace_data.virtual_lab_id,
                recent_workspace_data.project_id,
                group_repo,
            )
            # Get the updated_at from the preference
            updated_at = preference.updated_at if preference else None

        if not workspace:
            # Find default workspace: last created project in user's virtual lab
            workspace = await _find_default_workspace(session, user_id, group_repo)

        # Fetch full objects if workspace exists
        virtual_lab = None
        project = None
        if workspace:
            # Get full virtual lab details
            vl_result = await session.execute(
                select(VirtualLab).where(VirtualLab.id == workspace.virtual_lab_id)
            )
            vl_obj = vl_result.scalar_one_or_none()
            if vl_obj:
                virtual_lab = VirtualLabDetails.model_validate(vl_obj)

            # Get full project details
            proj_result = await session.execute(
                select(Project).where(Project.id == workspace.project_id)
            )
            proj_obj = proj_result.scalar_one_or_none()
            if proj_obj:
                project = ProjectVlOut.model_validate(proj_obj)

        recent_workspace = RecentWorkspaceOutWithDetails(
            user_id=user_id,
            workspace=workspace,
            updated_at=updated_at,
            virtual_lab=virtual_lab,
            project=project,
        )

        return VliResponse.new(
            message="Recent workspace retrieved successfully",
            data=RecentWorkspaceResponseWithDetails(
                recent_workspace=recent_workspace
            ).model_dump(),
        )

    except Exception as e:
        logger.exception(
            f"Error retrieving recent workspace for user {user_id}: {str(e)}"
        )
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while retrieving recent workspace",
        )


async def _validate_workspace_access(
    session: AsyncSession,
    user_id: UUID4,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    group_repo: GroupQueryRepository,
) -> Optional[Workspace]:
    """
    Validate that user has access to the stored workspace.

    Args:
        session: Database session
        user_id: User ID
        workspace_data: Workspace data from preference
        group_repo: Group repository

    Returns:
        Workspace if valid, None otherwise
    """
    try:
        # Check if virtual lab and project exist and are not deleted
        result = await session.execute(
            select(VirtualLab, Project)
            .join(Project, VirtualLab.id == Project.virtual_lab_id)
            .where(
                VirtualLab.id == virtual_lab_id,
                VirtualLab.deleted.is_(False),
                Project.id == project_id,
                Project.deleted.is_(False),
            )
        )
        vl_project = result.first()

        if not vl_project:
            return None

        virtual_lab, project = vl_project

        # Check if user has access to both virtual lab and project
        # Execute all group user retrieval calls in parallel
        vl_admin_task = group_repo.a_retrieve_group_users(
            str(virtual_lab.admin_group_id)
        )
        vl_member_task = group_repo.a_retrieve_group_users(
            str(virtual_lab.member_group_id)
        )
        proj_admin_task = group_repo.a_retrieve_group_users(str(project.admin_group_id))
        proj_member_task = group_repo.a_retrieve_group_users(
            str(project.member_group_id)
        )

        # Wait for all calls to complete concurrently
        (
            vl_admin_users,
            vl_member_users,
            proj_admin_users,
            proj_member_users,
        ) = await asyncio.gather(
            vl_admin_task, vl_member_task, proj_admin_task, proj_member_task
        )

        vl_user_ids = [u.id for u in vl_admin_users + vl_member_users]
        proj_user_ids = [u.id for u in proj_admin_users + proj_member_users]

        if str(user_id) in vl_user_ids and str(user_id) in proj_user_ids:
            return Workspace(virtual_lab_id=virtual_lab_id, project_id=project_id)

        return None

    except Exception as e:
        logger.warning(f"Error validating workspace access: {str(e)}")
        return None


async def _find_default_workspace(
    session: AsyncSession, user_id: UUID4, group_repo: GroupQueryRepository
) -> Optional[Workspace]:
    """
    Find the default workspace: last created project in user's virtual lab.
    Each user owns only one virtual lab.

    Args:
        session: Database session
        user_id: User ID
        group_repo: Group repository

    Returns:
        Default workspace if found
    """
    try:
        # Get user's groups to find virtual labs they own
        user_groups = await group_repo.a_retrieve_user_groups(str(user_id))
        user_group_ids = [str(g.id) for g in user_groups]

        if not user_group_ids:
            return None

        # Find the user's virtual lab (user should own only one)
        vl_result = await session.execute(
            select(VirtualLab)
            .where(
                VirtualLab.admin_group_id.in_(user_group_ids),
                VirtualLab.deleted.is_(False),
            )
            .limit(1)  # User should own only one virtual lab
        )

        user_virtual_lab = vl_result.scalar_one_or_none()

        if not user_virtual_lab:
            return None

        # Find the last created project in the user's virtual lab
        project_result = await session.execute(
            select(Project)
            .where(
                Project.virtual_lab_id == user_virtual_lab.id,
                Project.deleted.is_(False),
            )
            .order_by(Project.created_at.desc())
            .limit(1)
        )

        project = project_result.scalar_one_or_none()
        if project:
            return Workspace(virtual_lab_id=user_virtual_lab.id, project_id=project.id)

        return None

    except Exception as e:
        logger.warning(f"Error finding default workspace: {str(e)}")
        return None
