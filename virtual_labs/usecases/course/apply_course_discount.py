"""Apply a compute-usage discount to a course's virtual lab.

Service-admin operation. Grants the course's virtual lab a reduced compute
rate at the accounting service for the course window.

The discount window is always the course's own start/end dates. If the
course has no start_date or end_date set, the request is refused.

This is a thin wrapper over `accounting.create_virtual_lab_discount`: the
call is not idempotent, so each invocation creates a new discount row at
the accounting service.

Accounting failures are never surfaced verbatim. `_map_accounting_error`
logs the upstream detail and returns a stable message mapped to this
endpoint's contract: upstream 4xx -> 400, upstream 5xx -> 502, and a
connection error / timeout -> 503.
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

# Stable, downstream-agnostic messages returned to API callers. The detailed
# accounting error (upstream response body / exception text) is only logged.
_MSG_INVALID = (
    "The discount request was rejected as invalid by the accounting service."
)
_MSG_UPSTREAM_FAILURE = (
    "The accounting service could not apply the discount. Please try again later."
)
_MSG_UNAVAILABLE = (
    "The accounting service is currently unavailable. Please try again later."
)


def _map_accounting_error(
    ex: AccountingError, course_id: UUID, virtual_lab_id: UUID
) -> VliError:
    """Translate an accounting failure into this endpoint's 4xx/502/503 contract.

    The raw ``ex.message`` is built from the upstream response and must never
    reach the caller, so it is logged here and a stable message is returned.
    """
    upstream_status = ex.http_status_code
    logger.error(
        f"Failed to apply discount to course {course_id} (vlab {virtual_lab_id}): "
        f"upstream_status={upstream_status} detail={ex}"
    )

    retryable = upstream_status in (
        HTTPStatus.REQUEST_TIMEOUT,
        HTTPStatus.TOO_MANY_REQUESTS,
    )
    is_client_error = (
        upstream_status is not None and 400 <= upstream_status < 500 and not retryable
    )

    if is_client_error:
        # Accounting rejected the request payload itself (bad window/discount).
        return VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            message=_MSG_INVALID,
            http_status_code=HTTPStatus.BAD_REQUEST,
        )

    if upstream_status is not None and not retryable:
        # A 5xx (or unexpected status): accounting is up but failed to process.
        return VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            message=_MSG_UPSTREAM_FAILURE,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )

    # No upstream status (connection error / timeout) or an explicit
    # retry-after signal: accounting is unreachable, not a bad request.
    return VliError(
        error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
        message=_MSG_UNAVAILABLE,
        http_status_code=HTTPStatus.SERVICE_UNAVAILABLE,
    )


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

    valid_from = course.start_date
    valid_to = course.end_date

    if valid_from is None or valid_to is None:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message=(
                "The course must have both a start_date and an end_date set "
                "before a discount can be applied"
            ),
        )

    try:
        result = await accounting_cases.create_virtual_lab_discount(
            virtual_lab_id=course.virtual_lab_id,
            discount=payload.discount,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    except AccountingError as ex:
        raise _map_accounting_error(ex, course_id, course.virtual_lab_id) from ex

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
            valid_to=data.valid_to or valid_to,
        ),
    )
