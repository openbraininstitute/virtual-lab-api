"""Shared building blocks for the user-vlab endpoints.

`get_my_virtual_lab`, `list_tenant_virtual_labs`, and
`list_pending_virtual_labs` all need the same two primitives:

  * an enrichment step that turns a raw `VirtualLab` row into a
    `VirtualLabDetails` payload with `projects_count` and `course`
    populated, and
  * a paginated `SELECT` over non-deleted vlabs restricted to a UUID
    set with an optional `ILIKE` filter.

Keeping these here means each use case file stays focused on its own
flow without re-implementing the basics.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from virtual_labs.domain.common import PageParams
from virtual_labs.domain.labs import Course, VirtualLabDetails
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.repositories.project_repo import ProjectQueryRepository


async def enrich_vlab(
    vlab: VirtualLab, pqr: ProjectQueryRepository
) -> VirtualLabDetails:
    """Compose a `VirtualLabDetails` for one row.

    Only the projects count needs an extra fetch (one cheap DB
    aggregate). No Keycloak round-trip.
    """
    projects = await pqr.retrieve_projects_per_lab_count(
        virtual_lab_id=UUID(str(vlab.id))
    )
    return VirtualLabDetails(
        **{c.name: getattr(vlab, c.name) for c in vlab.__table__.columns},
        projects_count=projects,
        course=Course(
            template_project_id=vlab.course_template_project_id,
            is_initialized=vlab.is_course_initialized,
        ),
    )


async def enrich_many(
    vlabs: list[VirtualLab], pqr: ProjectQueryRepository
) -> list[VirtualLabDetails]:
    """Fan out enrichment over a page — one DB aggregate per row, all
    in flight concurrently."""
    return list(await asyncio.gather(*(enrich_vlab(v, pqr) for v in vlabs)))


_DEFAULT_ORDER: tuple[ColumnElement[Any], ...] = (
    VirtualLab.updated_at.desc(),
    VirtualLab.created_at.desc(),
)


async def list_vlabs_by_id(
    session: AsyncSession,
    *,
    vlab_ids: set[UUID],
    query: str | None,
    pagination: PageParams,
    extra_conditions: list[ColumnElement[bool]] | None = None,
    order_by: tuple[ColumnElement[Any], ...] | None = None,
) -> tuple[list[VirtualLab], int]:
    """Paginated, optionally filtered SELECT restricted to a UUID set.

    Returns ``(rows, total)``. Empty access set short-circuits to
    ``([], 0)`` without emitting SQL.

    * ``extra_conditions`` is appended to the ``WHERE`` clause as-is.
    * ``order_by`` overrides the default ``updated_at DESC,
      created_at DESC`` ordering. ``VirtualLab.id ASC`` is always
      appended last as a stable tiebreaker — without it pages of
      same-timestamp rows would shuffle between requests.
    """
    if not vlab_ids:
        return [], 0

    conditions: list[ColumnElement[bool]] = [
        ~VirtualLab.deleted,
        VirtualLab.id.in_(vlab_ids),
    ]
    if query:
        conditions.append(
            func.lower(VirtualLab.name).ilike(f"%{query.strip().lower()}%")
        )
    if extra_conditions:
        conditions.extend(extra_conditions)

    base = select(VirtualLab).where(and_(*conditions))

    total = (
        await session.scalar(select(func.count()).select_from(base.subquery()))
    ) or 0

    order_clauses: tuple[ColumnElement[Any], ...] = (
        *(order_by or _DEFAULT_ORDER),
        VirtualLab.id.asc(),
    )

    rows = (
        await session.scalars(
            base.order_by(*order_clauses)
            .offset((pagination.page - 1) * pagination.size)
            .limit(pagination.size)
        )
    ).all()

    return list(rows), total
