"""Update a draft course."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseOut, CourseUpdateBody
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.models import AuthUser


async def update_course(
    db: AsyncSession,
    course_id: UUID,
    payload: CourseUpdateBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Update mutable fields on a course. Only draft courses can be updated."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()

    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )

    try:
        course.ensure_mutable()
    except ValueError as e:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message=str(e),
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    await db.commit()
    await db.refresh(course)

    logger.info(f"Course {course_id} updated by user {auth[0].sub}")

    return VliAppResponse[CourseOut](
        message="Course updated successfully",
        data=CourseOut.model_validate(course),
    )
