"""Platform-admin operations over realm users.

The user directory lives in Keycloak; the DB only knows labs and
projects. The overview endpoint stitches the two together: fetch the
KC profile and groups, parse the group paths with the same `Grants`
parser the JWT flow uses, then resolve lab/project names from the DB.
"""

import asyncio
from http import HTTPStatus

from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.domain.admin import (
    AdminUserDetails,
    AdminUserProjectMembership,
    AdminUsersListQuery,
    AdminUserVlabMembership,
)
from virtual_labs.domain.common import PaginatedResponse
from virtual_labs.infrastructure.kc.grant import Grants
from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.repositories.labs import get_virtual_lab_names
from virtual_labs.repositories.project_repo import ProjectQueryRepository
from virtual_labs.repositories.user_repo import UserQueryRepository


async def list_users(
    params: AdminUsersListQuery,
) -> PaginatedResponse[UserRepresentation]:
    repo = UserQueryRepository()
    users, total = await asyncio.gather(
        repo.a_list_users(
            search=params.query, offset=params.offset, limit=params.page_size
        ),
        repo.a_count_users(search=params.query),
    )
    return PaginatedResponse.build(
        items=users, total=total, page=params.page, size=params.page_size
    )


async def get_user(session: AsyncSession, user_id: UUID4) -> AdminUserDetails:
    repo = UserQueryRepository()
    try:
        user, groups = await asyncio.gather(
            repo.a_retrieve_user_from_kc(str(user_id)),
            repo.a_retrieve_user_groups(user_id),
        )
    except IdentityError as error:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"User {user_id} not found in Keycloak",
            details=error.detail,
        )

    paths = [group.path for group in groups]
    grants = Grants.from_groups(paths)

    lab_ids = sorted(grants.virtual_labs.all)
    lab_names = await get_virtual_lab_names(session, lab_ids)
    virtual_labs = [
        AdminUserVlabMembership(
            id=lab_id,
            name=lab_names.get(lab_id),
            role=grants.virtual_labs.role_for(lab_id) or "member",
        )
        for lab_id in lab_ids
    ]

    project_ids = sorted(grants.projects.all)
    project_rows = await ProjectQueryRepository(session).get_project_names(project_ids)
    project_names = {
        project_id: (name, vlab_id) for project_id, name, vlab_id in project_rows
    }
    projects = []
    for project_id in project_ids:
        name, vlab_from_db = project_names.get(project_id, (None, None))
        projects.append(
            AdminUserProjectMembership(
                id=project_id,
                name=name,
                virtual_lab_id=grants.projects.vlab_of(project_id) or vlab_from_db,
                role=grants.projects.role_for(project_id) or "member",
            )
        )

    return AdminUserDetails(
        user=user,
        groups=paths,
        virtual_labs=virtual_labs,
        projects=projects,
    )
