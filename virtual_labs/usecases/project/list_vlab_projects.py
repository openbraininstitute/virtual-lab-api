"""List the projects in a virtual lab that the requester can see.

Authorization arrives via the `virtuallab_access` gate; the use case
itself only translates that decision into a database scope:

  * vlab admin → unrestricted scope (every project in the vlab),
  * everyone else → restricted to project IDs the JWT explicitly
    lists in `auth.grants.projects.all`.

"""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from fastapi.responses import Response
from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.common import PageParams, PaginatedResponse
from virtual_labs.domain.project import Project
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.repositories.project_repo import ProjectQueryRepository


def _accessible_project_ids(
    auth_user: AuthUserGrants, virtual_lab_id: UUID4
) -> set[UUID] | None:
    """DB scope for this requester.

    `None` means "every project in the vlab" (the caller is a vlab
    admin per the JWT). Otherwise the caller sees exactly the
    projects whose group memberships the JWT surfaces.
    """
    if auth_user.is_vlab_admin(virtual_lab_id):
        return None
    return set(auth_user.grants.projects.all)


async def list_vlab_projects_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    auth: tuple[AuthUserGrants, str],
    search: str | None,
    pagination: PageParams,
) -> Response:
    user, _token = auth

    try:
        result = await ProjectQueryRepository(session).list_vlab_projects_for_user(
            virtual_lab_id=virtual_lab_id,
            accessible_project_ids=_accessible_project_ids(user, virtual_lab_id),
            search=search,
            pagination=pagination,
        )
    except SQLAlchemyError as exc:
        logger.exception(f"DB error listing projects in vlab {virtual_lab_id}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to list projects",
        )

    items = [Project.model_validate(p) for p in result.rows]
    payload = PaginatedResponse.build(
        items=items,
        total=result.count,
        page=pagination.page,
        size=pagination.size,
    )

    return VliResponse.new(
        message="Virtual lab projects found" if items else "No projects matched",
        data=payload.model_dump(),
    )
