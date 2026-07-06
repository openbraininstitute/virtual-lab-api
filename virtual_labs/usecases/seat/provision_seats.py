"""Provision seats for a course.

Creates the requested number of seat records. Credits are granted
on assignment, not on provisioning.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import ProvisionSeatsBody, ProvisionSeatsResponse, SeatOut
from virtual_labs.infrastructure.db.models import Course, CourseStatus, Seat
from virtual_labs.infrastructure.settings import settings


async def provision_seats(
    db: AsyncSession,
    payload: ProvisionSeatsBody,
) -> VliAppResponse[ProvisionSeatsResponse]:
    # 1. Validate course exists
    result = await db.execute(select(Course).where(Course.id == payload.course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {payload.course_id} not found. Cannot provision seats without a valid course.",
        )

    # 2. Validate course is active
    if course.status != CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=(
                f"Course {payload.course_id} is in '{course.status.value}' status. "
                f"Seats can only be provisioned for active courses."
            ),
        )

    # 3. Create seat records
    batch_id = uuid.uuid4()
    expiry_date = datetime.now(timezone.utc) + timedelta(days=settings.SEAT_EXPIRY_DAYS)
    credit_value = course.credits_per_seat
    seats: list[Seat] = []
    for _ in range(payload.number_of_seats):
        seat = Seat(
            course_id=course.id,
            institution_id=course.institution_id,
            batch_id=batch_id,
            expiry_date=expiry_date,
            credit_value=credit_value,  # Store to block transfers to courses of higher credit value per seat
        )
        db.add(seat)
        seats.append(seat)

    await db.flush()

    await db.commit()

    for s in seats:
        await db.refresh(s)

    seat_outputs = [SeatOut.model_validate(s) for s in seats]

    return VliAppResponse(
        message=f"Successfully provisioned {payload.number_of_seats} seats",
        data=ProvisionSeatsResponse(
            seats=seat_outputs,
        ),
    )
