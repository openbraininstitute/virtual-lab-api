"""Update a draft course."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import ledger_container
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseOut, CourseUpdateBody
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.settings import settings
from virtual_labs.usecases.course.pro_discount import (
    apply_pro_discount,
    make_pro_discount_compensation,
)


async def update_course(
    db: AsyncSession,
    course_id: UUID,
    payload: CourseUpdateBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Update fields on a course, regardless of its status.

    Applies the same date-ordering checks as course activation. When the
    course window (start/end date) changes, the pro discount on the course's
    virtual lab is re-applied so its validity keeps mirroring the window.
    """
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()

    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )

    previous_start, previous_end = course.start_date, course.end_date

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(course, field, value)

    try:
        course.validate_dates()
    except ValueError as e:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message=str(e),
        )

    window_changed = (
        course.start_date != previous_start or course.end_date != previous_end
    )

    async with ledger_container() as comp:
        if window_changed:
            await apply_pro_discount(
                course.virtual_lab_id,
                valid_from=course.start_date,
                valid_to=course.end_date,
                failure_message=(
                    "Course update failed: could not update the pro discount"
                ),
            )
            comp.push(
                make_pro_discount_compensation(
                    course.virtual_lab_id,
                    discount=settings.COURSE_PRO_DISCOUNT,
                    valid_from=previous_start,
                    valid_to=previous_end,
                )
            )
        await db.commit()

    await db.refresh(course)

    logger.info(f"Course {course_id} updated by user {auth[0].sub}")

    return VliAppResponse[CourseOut](
        message="Course updated successfully",
        data=CourseOut.model_validate(course),
    )
