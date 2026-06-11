"""Claim an enrolment — student validates their link and we record who claimed it."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.infrastructure.db.models import CourseEnrolment, CourseStatus


async def claim_enrolment(
    db: AsyncSession,
    *,
    course_id: UUID,
    enrolment_id: UUID,
    user_id: UUID,
) -> CourseEnrolment:
    """Validate the claim link and set `claimed_by` on the enrolment.

    Checks:
    1. Enrolment exists and belongs to this course.
    2. Enrolment is not dropped.
    3. Enrolment is not already claimed.
    4. Course is active.

    Returns the updated enrolment.
    """
    result = await db.execute(
        select(CourseEnrolment)
        .where(
            CourseEnrolment.id == enrolment_id,
            CourseEnrolment.course_id == course_id,
        )
        .with_for_update()
    )
    enrolment = result.scalar_one_or_none()

    if enrolment is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Enrolment not found for this course",
        )

    if enrolment.is_dropped:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="This enrolment has been dropped",
        )

    if enrolment.claimed_by is not None:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="This enrolment has already been claimed",
        )

    # Verify the course is still active
    course = enrolment.course
    if course.status != CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Cannot claim enrolment: course is in '{course.status.value}' status",
        )

    now = datetime.now(timezone.utc)
    if course.end_date is not None and now >= course.end_date:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Cannot claim enrolment: course has ended",
        )

    enrolment.claimed_by = user_id
    await db.commit()

    logger.info(
        f"Enrolment {enrolment_id} claimed by user {user_id} (course={course_id})"
    )

    return enrolment
