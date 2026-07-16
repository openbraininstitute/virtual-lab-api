from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import SeatOut, TransferSeatsBody, TransferSeatsResponse
from virtual_labs.infrastructure.db.models import Course, CourseStatus, Seat


async def transfer_seats(
    db: AsyncSession,
    payload: TransferSeatsBody,
) -> VliAppResponse[TransferSeatsResponse]:
    if payload.source_course_id == payload.target_course_id:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Source and target courses must be different",
        )

    result = await db.execute(
        select(Course).where(
            Course.id.in_([payload.source_course_id, payload.target_course_id])
        )
    )
    courses = {course.id: course for course in result.scalars().all()}

    source_course = courses.get(payload.source_course_id)
    target_course = courses.get(payload.target_course_id)
    if source_course is None or target_course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="One or both courses were not found",
        )

    if source_course.institution_id != target_course.institution_id:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Both courses must belong to the same institution",
        )

    if (
        source_course.status != CourseStatus.ACTIVE
        or target_course.status != CourseStatus.ACTIVE
    ):
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Both courses must be active",
        )

    now = datetime.now(timezone.utc)
    if source_course.last_drop_date is None or now <= source_course.last_drop_date:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Source course must be past its last drop date",
        )

    if target_course.last_drop_date is None or now > target_course.last_drop_date:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Target course must be before its last drop date",
        )

    available_filter = [
        Seat.course_id == payload.source_course_id,
        Seat.is_consumed.is_(False),
        Seat.enrolment_id.is_(None),
        Seat.expiry_date > now,
        Seat.credit_value <= target_course.credits_per_seat,
    ]

    query = (
        select(Seat)
        .where(*available_filter)
        .order_by(Seat.expiry_date.asc())
        .with_for_update(skip_locked=True)
    )
    if payload.amount != "all":
        query = query.limit(payload.amount)

    locked_result = await db.execute(query)
    seats_to_transfer = list(locked_result.scalars().all())

    if payload.amount != "all" and len(seats_to_transfer) < payload.amount:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Requested {payload.amount} seats but only {len(seats_to_transfer)} available",
        )

    if not seats_to_transfer:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="No transferable seats available",
        )

    seat_ids = [seat.id for seat in seats_to_transfer]

    await db.execute(
        update(Seat)
        .where(Seat.id.in_(seat_ids))
        .values(course_id=payload.target_course_id)
    )
    await db.commit()

    for seat in seats_to_transfer:
        seat.course_id = payload.target_course_id

    return VliAppResponse(
        message="Successfully transferred seats",
        data=TransferSeatsResponse(
            transferred_count=len(seats_to_transfer),
            transferred_seats=[
                SeatOut.model_validate(seat) for seat in seats_to_transfer
            ],
        ),
    )
