"""Drop (release) seats for students in a course."""

from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.course import DropSeatsBody, SeatDropResult
from virtual_labs.infrastructure.db.models import Course


async def drop_seats(
    db: AsyncSession,
    *,
    course: Course,
    payload: DropSeatsBody,
) -> list[SeatDropResult]:
    """Drop seats for the given student_ids.

    TODO: Implement the actual drop logic:
    - Find seats linked to projects named after the student_ids
    - Soft-delete the project
    - Mark seat as no longer active
    - Best-effort reverse budget transfer
    """
    raise NotImplementedError("drop_seats usecase not yet implemented")
