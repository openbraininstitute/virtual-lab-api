"""List seats for a course."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.domain.seat import ListSeatsResponse, SeatDetailOut
from virtual_labs.infrastructure.db.models import Project, Seat


async def list_seats(
    db: AsyncSession,
    course_id: UUID,
) -> ListSeatsResponse:
    result = await db.execute(
        select(Seat)
        .outerjoin(Project, Seat.active_project_id == Project.id)
        .where(Seat.course_id == course_id)
        .options(joinedload(Seat.project))
        .order_by(Project.created_at.asc().nulls_last())
    )
    seats = result.scalars().all()

    return ListSeatsResponse(
        seats=[SeatDetailOut.model_validate(s) for s in seats],
    )
