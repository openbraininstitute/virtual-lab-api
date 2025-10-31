from typing import Annotated, Dict, List, Tuple

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from httpx import AsyncClient
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import (
    verify_project_read,
    verify_vlab_or_project_write,
    verify_vlab_read,
    verify_vlab_write,
)
from virtual_labs.core.authorization.verify_vlab_or_project_read import (
    verify_vlab_or_project_read,
)
from virtual_labs.core.exceptions.api_error import VliError
from virtual_labs.core.types import UserGroup, UserRoleEnum, VliAppResponse
from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
from virtual_labs.domain.invite import InvitePayload
from virtual_labs.domain.labs import InvitationResponse
from virtual_labs.domain.project import (
    AddUserToProjectIn,
    ProjectCreationBody,
    ProjectDeletionOut,
    ProjectExistenceOut,
    ProjectOut,
    ProjectPerVLCountOut,
    ProjectStats,
    ProjectsWithWorkspaceResponse,
    ProjectUpdateBody,
    ProjectUpdateRoleOut,
    ProjectUserDeleteOut,
    ProjectUserOperationsResponse,
    ProjectUsersCountOut,
    ProjectUsersOut,
    ProjectVlOut,
    ProjectWithStarredDateOut,
    ProjectWithVLOut,
)
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.transport.httpx import httpx_factory
from virtual_labs.shared.utils.auth import get_user_id_from_auth
from virtual_labs.usecases import project as project_cases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Project Endpoints"],
)


@router.get(
    "/projects",
    operation_id="get_all_user_projects",
    summary="Retrieve all projects for the authenticated user (only allowed projects)",
    description="Returns paginated list of projects with information about the user's last visited workspace",
    response_model=VliAppResponse[ProjectsWithWorkspaceResponse],
)
async def retrieve_all_projects(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=0),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_all_user_projects_use_case(
        session, auth, pagination=PageParams(page=page, size=size)
    )


@router.get(
    "/projects/_search",
    operation_id="search_all_projects",
    summary="Fulltext search for all allowed projects for the authenticated user",
    response_model=VliAppResponse[ProjectWithVLOut],
)
async def search_projects(
    q: str = Query(max_length=50, description="query string"),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.search_projects_by_name_use_case(
        session, auth=auth, query_term=q
    )


@router.get(
    "/projects/stars",
    operation_id="get_star_projects",
    summary="Retrieve star projects",
    description=(
        """
        Allow only the User that has the right role (be part of the project)
        Retrieve the star projects for a specific user
        """
    ),
    response_model=VliAppResponse[PaginatedResultsResponse[ProjectWithStarredDateOut]],
)
async def retrieve_stars_project(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=0),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_starred_projects_use_case(
        session,
        auth,
        pagination=PageParams(
            page=page,
            size=size,
        ),
    )


@router.get(
    "/{virtual_lab_id}/projects/_check",
    operation_id="check_project_existence_in_vlab",
    summary="Look for projects with the same name (case insensitive) in the same virtual lab",
    response_model=VliAppResponse[ProjectExistenceOut],
)
async def check_project_existence(
    virtual_lab_id: UUID4,
    q: str | None = Query("", description="query string"),
    session: AsyncSession = Depends(default_session_factory),
    _: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.check_project_existence_use_case(
        session,
        virtual_lab_id,
        query_term=q,
    )


@router.get(
    "/{virtual_lab_id}/projects/_search",
    operation_id="search_projects_per_vl",
    summary="Fulltext search for only allowed projects per virtual lab for the authenticated user",
    response_model=VliAppResponse[ProjectWithVLOut],
)
@verify_vlab_read
async def search_projects_per_virtual_lab(
    virtual_lab_id: UUID4,
    q: str = Query("", description="query string"),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.search_projects_per_virtual_lab_by_name_use_case(
        session, virtual_lab_id, auth=auth, query_term=q
    )


@router.get(
    "/{virtual_lab_id}/projects/count",
    operation_id="get_project_per_vl_count",
    summary="Retrieve virtual lab projects count",
    response_model=VliAppResponse[ProjectPerVLCountOut],
)
async def retrieve_projects_per_vl_count(
    virtual_lab_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    _: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_projects_count_per_virtual_lab_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
    )


@router.post(
    "/{virtual_lab_id}/projects",
    operation_id="create_new_project",
    summary="Create a new project for a virtual lab",
    description=(
        """
        Allow only the User that has the right role (based on KC groups 'Admin')  
        to create a new project for a specific virtual lab
        """
    ),
    response_model=VliAppResponse[ProjectOut],
)
@verify_vlab_write
async def create_new_project(
    virtual_lab_id: UUID4,
    payload: ProjectCreationBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.create_new_project_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        payload=payload,
        auth=auth,
    )


@router.get(
    "/{virtual_lab_id}/projects",
    operation_id="get_all_user_projects_per_vl",
    summary="Retrieve all projects per virtual lab for the authenticated user (only allowed projects)",
    response_model=VliAppResponse[PaginatedResultsResponse[ProjectVlOut]],
)
async def retrieve_projects(
    virtual_lab_id: UUID4,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=0),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_all_user_projects_per_vl_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        auth=auth,
        pagination=PageParams(
            page=page,
            size=size,
        ),
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="update_project_data",
    summary="Update project data",
    response_model=VliAppResponse[ProjectVlOut],
)
@verify_vlab_or_project_write
async def update_project_data(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    payload: ProjectUpdateBody,
    httpx_client: AsyncClient = Depends(httpx_factory),
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.update_project_data(
        session,
        httpx_client,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        payload=payload,
        auth=auth,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="get_project_by_id",
    summary="Retrieve single project detail per virtual lab",
    response_model=VliAppResponse[ProjectVlOut],
)
@verify_vlab_or_project_read
async def retrieve_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_single_project_use_case(
        session,
        virtual_lab_id,
        project_id,
        auth=auth,
    )


@router.delete(
    "/{virtual_lab_id}/projects/{project_id}",
    operation_id="delete_project",
    summary="Delete project of a virtual lab if the user has permission",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Admin")
        to delete a project from a specific virtual lab
        The deletion is logic so the data will be preserved in the db and only
        the `deleted`, `deleted_at` properties will be updated
        """
    ),
    response_model=VliAppResponse[ProjectDeletionOut],
)
@verify_vlab_or_project_write
async def delete_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.delete_project_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        auth=auth,
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/star-status",
    operation_id="star_or_unstar_project",
    summary="Star/Unstar (Pin/Unpin) project",
    tags=["Project Endpoints"],
    description=(
        """
        Allow only the User that has the right role (be part of the project)
        Star or Unstar (Pin/Unpin) a project
        """
    ),
    response_model=VliAppResponse[ProjectWithStarredDateOut],
)
@verify_vlab_or_project_read
async def update_project_star_status(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    value: Annotated[bool, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.update_star_project_status_use_case(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        value=value,
        auth=auth,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/stats",
    response_model=VliAppResponse[ProjectStats],
    summary="Get comprehensive statistics for a project",
)
@verify_project_read
async def get_project_stats(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> VliAppResponse[ProjectStats]:
    stats = await project_cases.get_project_stats(session, project_id)
    return VliAppResponse[ProjectStats](
        message="Statistics for project",
        data=stats,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users",
    operation_id="get_project_users",
    summary="Retrieve users per project",
    response_model=VliAppResponse[ProjectUsersOut],
)
@verify_vlab_or_project_read
async def retrieve_project_users(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_all_users_per_project_use_case(
        session, virtual_lab_id, project_id
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/invites",
    operation_id="post_invite_to_project",
    summary="Invite user to a project",
    response_model=VliAppResponse[InvitationResponse],
)
@verify_vlab_or_project_write
async def invite_user_to_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    payload: InvitePayload,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.invite_user_to_project(
        session=session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        inviter_id=get_user_id_from_auth(auth),
        invite_details=payload,
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/invites/cancel",
    operation_id="post_invite_to_project",
    summary="Invite user to a project",
    response_model=VliAppResponse[InvitationResponse],
)
@verify_vlab_write
async def cancel_project_invite_for_user(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    payload: InvitePayload,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.cancel_project_invite(
        session=session,
        project_id=project_id,
        payload=payload,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/users/count",
    operation_id="get_project_users_count",
    summary="Retrieve users count per project",
    response_model=VliAppResponse[ProjectUsersCountOut],
)
async def retrieve_project_users_count(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    _: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.retrieve_users_per_project_count_use_case(
        session,
        project_id,
    )


@router.patch(
    "/{virtual_lab_id}/projects/{project_id}/users/role",
    operation_id="update_user_role_in_project",
    summary="Update user role in the current project",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Virtual Lab Admin/Project Admin")
        to update the selected user role for the selected project
        if the user not in the group already, then operation will not be allowed
        """
    ),
    response_model=VliAppResponse[ProjectUpdateRoleOut],
)
@verify_vlab_or_project_write
async def update_user_role_in_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: Annotated[UUID4, Body(embed=True)],
    new_role: Annotated[UserRoleEnum, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.update_user_role_in_project(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        new_role=new_role,
        user_id=user_id,
        auth=auth,
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/users/detach",
    operation_id="detach_user_from_project",
    summary="Detach user from the project if the user has permission",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Virtual Lab Admin/Project Admin")
        to detach the selected user from the current project
        """
    ),
    response_model=VliAppResponse[ProjectUserDeleteOut],
)
@verify_vlab_or_project_write
async def detach_user_from_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    user_id: Annotated[UUID4, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.detach_user_from_project(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        user_id=user_id,
        auth=auth,
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/users/attach",
    operation_id="attach_user_to_project",
    summary="Attach user to the project if the user has permission",
    description=(
        """
        Allow only the User that has the right role (based on KC groups "Virtual Lab Admin/Project Admin")
        to attach the selected users to the current project
        """
    ),
    response_model=VliAppResponse[ProjectUserOperationsResponse],
)
@verify_vlab_or_project_write
async def attach_users_to_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    users: Annotated[List[AddUserToProjectIn], Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    return await project_cases.attach_users_to_project(
        session,
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        users=users,
        auth=auth,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/user-groups",
    operation_id="get_project_user_groups",
    summary="Get user's groups for a project",
    description="Get the groups the authenticated user is a part of for the specified project and its virtual lab (admin or member)",
    response_model=VliAppResponse[Dict[str, List[UserGroup]]],
)
async def get_user_groups_for_project(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(verify_jwt),
) -> Response | VliError:
    """
    Get the user groups for a project and its parent virtual lab.

    Args:
        virtual_lab_id: ID of the virtual lab
        project_id: ID of the project

    Returns:
        Response: List of user groups for the project and virtual lab
    """
    return await project_cases.get_user_project_groups(
        session=session, virtual_lab_id=virtual_lab_id, project_id=project_id, auth=auth
    )
