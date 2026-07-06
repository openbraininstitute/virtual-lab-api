"""Retrieve courses by ID or by virtual lab name."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseDetailOut
from virtual_labs.infrastructure.db.models import Course, VirtualLab


def _to_detail(course: Course) -> CourseDetailOut:
    """Map a Course (with loaded relationships) to CourseDetailOut."""
    return CourseDetailOut(
        id=course.id,
        virtual_lab_id=course.virtual_lab_id,
        virtual_lab_name=course.virtual_lab.name,
        institution_id=course.institution_id,
        institution_name=course.institution.name,
        template_project_id=course.template_project_id,
        status=course.status.value,
        start_date=course.start_date,
        end_date=course.end_date,
        last_drop_date=course.last_drop_date,
    )


async def get_course_by_id(
    db: AsyncSession,
    course_id: UUID,
) -> VliAppResponse[CourseDetailOut]:
    """Fetch a single course by its ID."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()

    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )

    return VliAppResponse[CourseDetailOut](
        message="Course retrieved successfully",
        data=_to_detail(course),
    )


async def search_courses_by_vlab_name(
    db: AsyncSession,
    vlab_name: str,
) -> VliAppResponse[list[CourseDetailOut]]:
    """Search courses by virtual lab name (case-insensitive partial match)."""
    result = await db.execute(
        select(Course)
        .join(Course.virtual_lab)
        .where(VirtualLab.name.ilike(f"%{vlab_name}%"))
    )
    courses = result.unique().scalars().all()

    return VliAppResponse[list[CourseDetailOut]](
        message=f"Found {len(courses)} course(s)",
        data=[_to_detail(c) for c in courses],
    )
