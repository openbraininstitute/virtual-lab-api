from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from httpx import AsyncClient
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.admin import AdminProjectDetails, AdminProjectsListQuery
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.domain.project import ProjectUpdateBody
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.grant import AuthUserGrants, parse_auth_grants
from virtual_labs.infrastructure.transport.httpx import httpx_factory
from virtual_labs.routes.admin.deps import PLATFORM_ADMIN_TAG_PREFIX, platform_admin
from virtual_labs.usecases.admin import projects as admin_projects

router = APIRouter(tags=[f"{PLATFORM_ADMIN_TAG_PREFIX} | Projects"])


@router.get(
    "/projects",
    response_model=PaginatedResponse[AdminProjectDetails],
    summary="List all projects across the platform",
)
async def list_projects(
    params: Annotated[AdminProjectsListQuery, Query()],
    session: AsyncSession = Depends(default_session_factory),
) -> PaginatedResponse[AdminProjectDetails]:
    return await admin_projects.list_projects(session, params)


@router.get(
    "/projects/{project_id}",
    response_model=AdminProjectDetails,
    summary="Get any project by id, including soft-deleted ones",
)
async def get_project(
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> AdminProjectDetails:
    return await admin_projects.get_project(session, project_id)


@router.get(
    "/projects/{project_id}/users",
    summary="List members of any project",
)
async def get_project_users(
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
) -> Response:
    return await admin_projects.get_project_users(session, project_id)


@router.patch(
    "/projects/{project_id}",
    summary="Update any project",
    dependencies=[Depends(platform_admin)],
)
async def update_project(
    project_id: UUID4,
    payload: ProjectUpdateBody,
    session: AsyncSession = Depends(default_session_factory),
    httpx_client: AsyncClient = Depends(httpx_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> Response:
    return await admin_projects.update_project(
        session, httpx_client, project_id, payload, actor=auth[0], token=auth[1]
    )


@router.delete(
    "/projects/{project_id}",
    summary="Soft-delete any project",
    dependencies=[Depends(platform_admin)],
)
async def delete_project(
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> Response:
    return await admin_projects.delete_project(
        session, project_id, actor=auth[0], token=auth[1]
    )


@router.post(
    "/projects/{project_id}/restore",
    response_model=AdminProjectDetails,
    summary="Restore a soft-deleted project",
    dependencies=[Depends(platform_admin)],
)
async def restore_project(
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> AdminProjectDetails:
    return await admin_projects.restore_project(session, project_id, actor=auth[0])


@router.patch(
    "/projects/{project_id}/users/{user_id}/role",
    summary="Change a member's role in any project",
    dependencies=[Depends(platform_admin)],
)
async def change_project_user_role(
    project_id: UUID4,
    user_id: UUID4,
    new_role: Annotated[UserRoleEnum, Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> Response:
    return await admin_projects.change_project_user_role(
        session, project_id, user_id, new_role, actor=auth[0], token=auth[1]
    )


@router.delete(
    "/projects/{project_id}/users/{user_id}",
    summary="Remove a member from any project",
    dependencies=[Depends(platform_admin)],
)
async def remove_project_user(
    project_id: UUID4,
    user_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUserGrants, str] = Depends(parse_auth_grants),
) -> Response:
    return await admin_projects.remove_project_user(
        session, project_id, user_id, actor=auth[0], token=auth[1]
    )
