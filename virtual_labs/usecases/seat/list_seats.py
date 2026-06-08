"""List seats for a course."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.seat import ListSeatsResponse, SeatOut
from virtual_labs.infrastructure.db.models import Seat


async def list_seats(
    db: AsyncSession,
    course_id: UUID,
) -> ListSeatsResponse:
    result = await db.execute(
        select(Seat).where(Seat.course_id == course_id).order_by(Seat.created_at)
    )
    seats = result.scalars().all()

    return ListSeatsResponse(
        seats=[SeatOut.model_validate(s) for s in seats],
    )
