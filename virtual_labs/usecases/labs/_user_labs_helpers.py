"""Shared building blocks for the user-vlab endpoints.

`get_my_virtual_lab`, `list_vlabs_by_id`, and
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

from virtual_labs.domain.common import PaginationRequest
from virtual_labs.domain.labs import VirtualLabDetails
from virtual_labs.infrastructure.db.models import Project, VirtualLab


async def enrich_vlab(
    vlab: VirtualLab, projects_count: int | None = None
) -> VirtualLabDetails:
    """Compose a `VirtualLabDetails` for one row.

    Only the projects count needs an extra fetch (one cheap DB
    aggregate). No Keycloak round-trip.
    """
    return VirtualLabDetails.model_validate(vlab).model_copy(
        update={
            "projects_count": projects_count,
        },
    )


async def project_counts_by_vlab(
    session: AsyncSession, vlab_ids: list[UUID]
) -> dict[UUID, int]:
    if not vlab_ids:
        return {}

    rows = (
        await session.execute(
            select(Project.virtual_lab_id, func.count(Project.id))
            .where(
                and_(
                    Project.virtual_lab_id.in_(vlab_ids),
                    Project.deleted.is_(False),
                )
            )
            .group_by(Project.virtual_lab_id)
        )
    ).all()
    return {UUID(str(virtual_lab_id)): count for virtual_lab_id, count in rows}


async def enrich_many(
    vlabs: list[VirtualLab], session: AsyncSession
) -> list[VirtualLabDetails]:
    """Compose enriched domain payloads for one page."""
    counts = await project_counts_by_vlab(session, [UUID(str(v.id)) for v in vlabs])
    return list(
        await asyncio.gather(
            *(enrich_vlab(v, counts.get(UUID(str(v.id)), 0)) for v in vlabs)
        )
    )


_DEFAULT_ORDER: tuple[ColumnElement[Any], ...] = (
    VirtualLab.updated_at.desc(),
    VirtualLab.created_at.desc(),
)


async def list_vlabs_by_id(
    session: AsyncSession,
    *,
    vlab_ids: set[UUID],
    query: str | None,
    pagination: PaginationRequest,
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
        VirtualLab.deleted.is_(False),
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
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).all()

    return list(rows), total
