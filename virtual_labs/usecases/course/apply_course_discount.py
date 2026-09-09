"""Apply a compute-usage discount to a course's virtual lab.

Service-admin operation. Grants the course's virtual lab a reduced compute
rate at the accounting service for the course window (or an explicit one).

This is a thin wrapper over `accounting.create_virtual_lab_discount`: the
call is not idempotent, so each invocation creates a new discount row at
the accounting service.
"""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.accounting_error import AccountingError
from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import ApplyCourseDiscountBody, CourseDiscountOut
from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import accounting as accounting_cases


async def apply_course_discount(
    db: AsyncSession,
    course_id: UUID,
    payload: ApplyCourseDiscountBody,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseDiscountOut]:
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )

    valid_from = payload.valid_from or course.start_date
    valid_to = payload.valid_to or course.end_date

    if valid_from is None:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=(
                "valid_from is required — the course has no start_date to fall "
                "back on"
            ),
        )
    if valid_to is not None and valid_from >= valid_to:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="valid_to must be after valid_from",
        )

    try:
        result = await accounting_cases.create_virtual_lab_discount(
            virtual_lab_id=course.virtual_lab_id,
            discount=payload.discount,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    except AccountingError as ex:
        logger.error(
            f"Failed to apply discount to course {course_id} "
            f"(vlab {course.virtual_lab_id}): {ex}"
        )
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            message=ex.message or "Could not apply the course discount",
            http_status_code=ex.http_status_code or HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    logger.info(
        f"Applied {payload.discount} discount to course {course_id} "
        f"(vlab {course.virtual_lab_id}) valid {valid_from} → {valid_to} "
        f"by user {auth[0].sub}"
    )

    data = result.data
    return VliAppResponse[CourseDiscountOut](
        message="Course discount applied successfully",
        data=CourseDiscountOut(
            virtual_lab_id=course.virtual_lab_id,
            discount=data.discount,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
        ),
    )
