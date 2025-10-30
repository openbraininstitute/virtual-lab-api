import asyncio
from http import HTTPStatus
from typing import Tuple

from fastapi import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.domain.project import ProjectVlOut
from virtual_labs.domain.user import SetRecentWorkspaceRequest
from virtual_labs.domain.workspace import (
    RecentWorkspaceOutWithDetails,
    RecentWorkspaceResponseWithDetails,
)
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_preference_repo import (
    UserPreferenceMutationRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def set_recent_workspace(
    request: SetRecentWorkspaceRequest,
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    """
    Set the user's recent workspace after validating access permissions.

    Args:
        request: Request containing workspace information
        auth: Authentication tuple
        session: Database session

    Returns:
        Response: Confirmation of workspace update
    """
    try:
        user_id = get_user_id_from_auth(auth)
        prefr = UserPreferenceMutationRepository(session)
        gqr = GroupQueryRepository()

        await _validate_workspace_access(
            session,
            user_id,
            request.workspace.virtual_lab_id,
            request.workspace.project_id,
            gqr,
        )

        preference = await prefr.set_recent_workspace(user_id, request.workspace)

        virtual_lab = None
        project = None

        vl_result = await session.execute(
            select(VirtualLab).where(VirtualLab.id == request.workspace.virtual_lab_id)
        )
        vl_obj = vl_result.scalar_one_or_none()
        if vl_obj:
            virtual_lab = VirtualLabDetails.model_validate(vl_obj)

        proj_result = await session.execute(
            select(Project).where(Project.id == request.workspace.project_id)
        )
        proj_obj = proj_result.scalar_one_or_none()

        if proj_obj is not None:
            admins = await gqr.a_retrieve_group_user_ids(
                group_id=proj_obj.admin_group_id
            )
            project = ProjectVlOut.model_validate(
                {**proj_obj.__dict__, "admins": admins}
            )

        recent_workspace = RecentWorkspaceOutWithDetails(
            user_id=user_id,
            workspace=request.workspace,
            updated_at=preference.updated_at,
            virtual_lab=virtual_lab,
            project=project,
        )

        return VliResponse.new(
            message="Recent workspace updated successfully",
            data=RecentWorkspaceResponseWithDetails(
                recent_workspace=recent_workspace
            ).model_dump(),
        )

    except VliError:
        raise
    except Exception as e:
        logger.exception(f"Error setting recent workspace for user {user_id}: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while setting recent workspace",
        )


async def _validate_workspace_access(
    session: AsyncSession,
    user_id: UUID4,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    group_repo: GroupQueryRepository,
) -> None:
    """
    Validate that user has access to the specified workspace.

    Args:
        session: Database session
        user_id: User ID
        virtual_lab_id: Virtual lab ID
        project_id: Project ID
        group_repo: Group repository

    Raises:
        VliError: If validation fails
    """
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
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Virtual lab or project not found",
        )

    virtual_lab, project = vl_project

    await group_repo.a_retrieve_user_groups(str(user_id))

    vl_admin_task = group_repo.a_retrieve_group_users(str(virtual_lab.admin_group_id))
    vl_member_task = group_repo.a_retrieve_group_users(str(virtual_lab.member_group_id))
    proj_admin_task = group_repo.a_retrieve_group_users(str(project.admin_group_id))
    proj_member_task = group_repo.a_retrieve_group_users(str(project.member_group_id))

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

    if str(user_id) not in vl_user_ids:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="User does not have access to the specified virtual lab",
        )

    if str(user_id) not in proj_user_ids:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.FORBIDDEN,
            message="User does not have access to the specified project",
        )
