"""Platform-admin operations over projects.

The member-scoped project usecases already implement update, delete
and membership management (including the Keycloak side); the admin
layer resolves the parent lab from the DB — the operator has no
membership groups to derive it from — then delegates and audit-logs.
"""

from http import HTTPStatus
from typing import Tuple

from fastapi.responses import Response
from httpx import AsyncClient
from pydantic import UUID4
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.admin import AdminProjectDetails, AdminProjectsListQuery
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.domain.project import ProjectUpdateBody
from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories.project_repo import (
    ProjectMutationRepository,
    ProjectQueryRepository,
)
from virtual_labs.usecases.admin._audit import log_admin_action
from virtual_labs.usecases.admin._ordering import order_clauses
from virtual_labs.usecases.project import (
    delete_project_use_case,
    detach_user_from_project,
    retrieve_all_users_per_project_use_case,
    update_project_data,
    update_user_role_in_project,
)


def _details(project: Project, virtual_lab: VirtualLab) -> AdminProjectDetails:
    return AdminProjectDetails.model_validate(project).model_copy(
        update={"virtual_lab_name": virtual_lab.name}
    )


async def _resolve(
    session: AsyncSession, project_id: UUID4
) -> Tuple[Project, VirtualLab]:
    try:
        project, virtual_lab = await ProjectQueryRepository(
            session
        ).retrieve_one_project_by_id(project_id=project_id)
    except NoResultFound:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Project not found",
        )
    return project, virtual_lab


async def list_projects(
    session: AsyncSession, params: AdminProjectsListQuery
) -> PaginatedResponse[AdminProjectDetails]:
    rows, total = await ProjectQueryRepository(session).admin_list_projects(
        query=params.query,
        virtual_lab_id=params.virtual_lab_id,
        include_deleted=params.include_deleted,
        deleted_only=params.deleted_only,
        pagination=params,
        order_by=order_clauses(Project, params.order_by, params.order_direction),
    )
    return PaginatedResponse.build(
        items=[_details(project, virtual_lab) for project, virtual_lab in rows],
        total=total,
        page=params.page,
        size=params.page_size,
    )


async def get_project(session: AsyncSession, project_id: UUID4) -> AdminProjectDetails:
    project, virtual_lab = await _resolve(session, project_id)
    return _details(project, virtual_lab)


async def get_project_users(session: AsyncSession, project_id: UUID4) -> Response:
    project, _ = await _resolve(session, project_id)
    return await retrieve_all_users_per_project_use_case(
        session, project.virtual_lab_id, project_id
    )


async def update_project(
    session: AsyncSession,
    httpx_client: AsyncClient,
    project_id: UUID4,
    payload: ProjectUpdateBody,
    actor: AuthUserGrants,
    token: str,
) -> Response:
    project, _ = await _resolve(session, project_id)
    response = await update_project_data(
        session,
        httpx_client,
        virtual_lab_id=project.virtual_lab_id,
        project_id=project_id,
        payload=payload,
        auth=(actor, token),
    )
    log_admin_action(
        actor,
        "project.update",
        "project",
        project_id,
        fields=sorted(payload.model_dump(exclude_unset=True)),
    )
    return response


async def delete_project(
    session: AsyncSession, project_id: UUID4, actor: AuthUserGrants, token: str
) -> Response:
    project, _ = await _resolve(session, project_id)
    response = await delete_project_use_case(
        session,
        virtual_lab_id=project.virtual_lab_id,
        project_id=project_id,
        auth=(actor, token),
    )
    log_admin_action(actor, "project.delete", "project", project_id)
    return response


async def restore_project(
    session: AsyncSession, project_id: UUID4, actor: AuthUserGrants
) -> AdminProjectDetails:
    query_repo = ProjectQueryRepository(session)
    project, virtual_lab = await _resolve(session, project_id)

    if not project.deleted:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Project is not deleted",
        )
    if virtual_lab.deleted:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message="Cannot restore a project of a deleted virtual lab",
        )
    conflicts = await query_repo.count_active_project_name_conflicts(
        virtual_lab_id=project.virtual_lab_id,
        name=project.name,
        exclude_project_id=project_id,
    )
    if conflicts:
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            message="Another non-deleted project with the same name exists in this virtual lab",
        )

    await ProjectMutationRepository(session).un_delete_project(
        virtual_lab_id=project.virtual_lab_id, project_id=project_id
    )
    log_admin_action(actor, "project.restore", "project", project_id)

    project, virtual_lab = await _resolve(session, project_id)
    return _details(project, virtual_lab)


async def change_project_user_role(
    session: AsyncSession,
    project_id: UUID4,
    user_id: UUID4,
    new_role: UserRoleEnum,
    actor: AuthUserGrants,
    token: str,
) -> Response:
    project, _ = await _resolve(session, project_id)
    response = await update_user_role_in_project(
        session,
        virtual_lab_id=project.virtual_lab_id,
        project_id=project_id,
        user_id=user_id,
        new_role=new_role,
        auth=(actor, token),
    )
    log_admin_action(
        actor,
        "project.user_role.update",
        "project",
        project_id,
        user_id=user_id,
        new_role=new_role.value,
    )
    return response


async def remove_project_user(
    session: AsyncSession,
    project_id: UUID4,
    user_id: UUID4,
    actor: AuthUserGrants,
    token: str,
) -> Response:
    project, _ = await _resolve(session, project_id)
    response = await detach_user_from_project(
        session,
        virtual_lab_id=project.virtual_lab_id,
        project_id=project_id,
        user_id=user_id,
        auth=(actor, token),
    )
    log_admin_action(
        actor, "project.user.remove", "project", project_id, user_id=user_id
    )
    return response
