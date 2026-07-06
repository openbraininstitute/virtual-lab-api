"""List enrolments for a course (teacher/vlab admin view)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.infrastructure.db.models import CourseEnrolment


async def list_enrolments(
    db: AsyncSession,
    course_id: UUID,
) -> list[CourseEnrolment]:
    """Return all enrolments for a course with their linked seat eagerly loaded."""
    result = await db.execute(
        select(CourseEnrolment)
        .where(CourseEnrolment.course_id == course_id)
        .options(joinedload(CourseEnrolment.seat))
        .order_by(CourseEnrolment.created_at.asc())
    )
    return list(result.scalars().unique().all())
