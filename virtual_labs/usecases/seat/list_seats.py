"""List seats for a course."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.domain.common import ListResponse, PaginationResponse
from virtual_labs.domain.seat import SeatDetailOut
from virtual_labs.infrastructure.db.models import Seat


async def list_seats(
    db: AsyncSession,
    course_id: UUID,
) -> ListResponse[SeatDetailOut]:
    result = await db.execute(
        select(Seat)
        .where(Seat.course_id == course_id)
        .options(joinedload(Seat.enrolment))
        .order_by(Seat.created_at.asc())
    )
    seats = result.scalars().unique().all()
    items = [SeatDetailOut.model_validate(s) for s in seats]

    return ListResponse[SeatDetailOut](
        data=items,
        pagination=PaginationResponse(
            page=1,
            page_size=len(items),
            total_items=len(items),
        ),
    )
