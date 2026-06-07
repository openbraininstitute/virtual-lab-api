"""Activate or void a course."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseOut
from virtual_labs.infrastructure.db.models import Course, CourseStatus
from virtual_labs.infrastructure.kc.models import AuthUser


async def _get_course(db: AsyncSession, course_id: UUID) -> Course:
    """Fetch course by ID or raise 404."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )
    return course


async def activate_course(
    db: AsyncSession,
    course_id: UUID,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Set course status to active. Only draft courses can be activated."""
    course = await _get_course(db, course_id)

    if course.status != CourseStatus.DRAFT:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Cannot activate course with status '{course.status.value}'. Only draft courses can be activated.",
        )

    course.status = CourseStatus.ACTIVE
    await db.commit()
    await db.refresh(course)

    logger.info(f"Course {course_id} activated by user {auth[0].sub}")

    return VliAppResponse[CourseOut](
        message="Course activated successfully",
        data=CourseOut.model_validate(course),
    )


async def void_course(
    db: AsyncSession,
    course_id: UUID,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Set course status to voided. Only draft or active courses can be voided."""
    course = await _get_course(db, course_id)

    if course.status == CourseStatus.VOIDED:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message="Course is already voided",
        )

    course.status = CourseStatus.VOIDED
    await db.commit()
    await db.refresh(course)

    logger.info(f"Course {course_id} voided by user {auth[0].sub}")

    return VliAppResponse[CourseOut](
        message="Course voided successfully",
        data=CourseOut.model_validate(course),
    )
