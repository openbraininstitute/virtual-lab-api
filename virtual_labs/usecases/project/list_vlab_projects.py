"""List the projects in a virtual lab that the requester can see.

Authorization arrives via the `virtuallab_access` gate; the use case
itself only translates that decision into a database scope:

  * vlab admin → unrestricted scope (every project in the vlab),
  * everyone else → restricted to project IDs the JWT explicitly
    lists in `auth.grants.projects.all`.

"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from uuid import UUID

from loguru import logger
from pydantic import UUID4, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.common import (
    ListResponse,
    OrderDirection,
    PaginationRequest,
    PaginationResponse,
    WorkspaceOrderBy,
)
from virtual_labs.domain.project import Project
from virtual_labs.infrastructure.db.models import Project as ProjectModel
from virtual_labs.infrastructure.kc.grant import AuthUserGrants


class ListVlabProjectsQuery(PaginationRequest):
    order_by: WorkspaceOrderBy = WorkspaceOrderBy.UPDATED_AT
    order_direction: OrderDirection = OrderDirection.DESC
    query: str | None = Field(default=None, min_length=1, max_length=200)


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


def _build_order_clauses(
    order_by: WorkspaceOrderBy,
    direction: OrderDirection,
    user_id: object,
) -> tuple[ColumnElement[Any], ...]:
    asc = direction is OrderDirection.ASC

    # Dropped projects always come last, regardless of the requested ordering.
    dropped_last = ProjectModel.is_dropped.asc()

    if order_by is WorkspaceOrderBy.OWNER:
        owner_expr = case((ProjectModel.owner_id == user_id, 0), else_=1)
        primary = owner_expr.asc() if asc else owner_expr.desc()
        return (
            dropped_last,
            primary,
            ProjectModel.updated_at.desc(),
            ProjectModel.created_at.desc(),
        )

    if order_by is WorkspaceOrderBy.CREATED_AT:
        col = ProjectModel.created_at
        return (dropped_last, col.asc() if asc else col.desc())

    if order_by is WorkspaceOrderBy.NAME:
        col = func.lower(ProjectModel.name)
        return (
            dropped_last,
            col.asc() if asc else col.desc(),
            ProjectModel.updated_at.desc(),
        )

    col = ProjectModel.updated_at
    return (
        dropped_last,
        col.asc() if asc else col.desc(),
        ProjectModel.created_at.desc(),
    )


async def list_vlab_projects_use_case(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    auth: tuple[AuthUserGrants, str],
    order_by: WorkspaceOrderBy,
    order_direction: OrderDirection,
    query: str | None,
    pagination: PaginationRequest,
) -> ListResponse[Project]:
    user, _token = auth

    try:
        accessible_project_ids = _accessible_project_ids(user, virtual_lab_id)
        if accessible_project_ids is not None and not accessible_project_ids:
            rows: list[ProjectModel] = []
            total = 0
        else:
            conditions = [
                ProjectModel.virtual_lab_id == virtual_lab_id,
                ~ProjectModel.deleted,
            ]
            if accessible_project_ids is not None:
                conditions.append(ProjectModel.id.in_(accessible_project_ids))
            if query:
                needle = f"%{query.strip().lower()}%"
                conditions.append(
                    or_(
                        func.lower(ProjectModel.name).ilike(needle),
                        func.lower(ProjectModel.description).ilike(needle),
                    )
                )

            base = select(ProjectModel).where(and_(*conditions))
            total = (
                await session.scalar(select(func.count()).select_from(base.subquery()))
            ) or 0
            rows = list(
                (
                    await session.scalars(
                        base.order_by(
                            *_build_order_clauses(order_by, order_direction, user.id),
                            ProjectModel.id.asc(),
                        )
                        .offset(pagination.offset)
                        .limit(pagination.page_size)
                    )
                ).all()
            )
    except SQLAlchemyError as exc:
        logger.exception(f"DB error listing projects in vlab {virtual_lab_id}: {exc}")
        raise VliError(
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Failed to list projects",
        )

    items = [Project.model_validate(p) for p in rows]
    return ListResponse[Project](
        data=items,
        pagination=PaginationResponse(
            page=pagination.page,
            page_size=len(items),
            total_items=total,
        ),
    )
