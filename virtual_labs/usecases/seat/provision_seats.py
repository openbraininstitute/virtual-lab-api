"""Provision seats for a course.

Creates the requested number of seat records and tops up the virtual lab
budget via the accounting service.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import ProvisionSeatsBody, ProvisionSeatsResponse, SeatOut
from virtual_labs.infrastructure.db.models import Course, Seat
from virtual_labs.infrastructure.settings import settings
from virtual_labs.usecases import accounting as accounting_cases


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

    # 2. Create seat records
    batch_id = uuid.uuid4()
    expiry_date = datetime.now(timezone.utc) + timedelta(days=settings.SEAT_EXPIRY_DAYS)
    seats: list[Seat] = []
    for _ in range(payload.number_of_seats):
        seat = Seat(
            course_id=course.id,
            institution_id=course.institution_id,
            batch_id=batch_id,
            expiry_date=expiry_date,
        )
        db.add(seat)
        seats.append(seat)

    await db.flush()

    # 3. Top up the virtual lab budget
    total_credits = payload.number_of_seats * settings.CREDITS_PER_SEAT

    if settings.ACCOUNTING_BASE_URL is not None:
        try:
            await accounting_cases.top_up_virtual_lab_budget(
                virtual_lab_id=course.virtual_lab_id,
                amount=total_credits,
            )
            logger.info(
                f"Topped up vlab {course.virtual_lab_id} with {total_credits} credits "
                f"for {payload.number_of_seats} seats (course {course.id})"
            )
        except Exception as ex:
            logger.error(
                f"Failed to top up vlab {course.virtual_lab_id} "
                f"for seat provisioning (course {course.id}): {ex}"
            )
            raise VliError(
                error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
                http_status_code=HTTPStatus.BAD_GATEWAY,
                message=f"Failed to top up virtual lab budget for course {course.id}",
                details=str(ex),
            ) from ex

    await db.commit()

    for s in seats:
        await db.refresh(s)

    seat_outputs = [SeatOut.model_validate(s) for s in seats]

    return VliAppResponse(
        message=f"Successfully provisioned {payload.number_of_seats} seats",
        data=ProvisionSeatsResponse(
            seats=seat_outputs,
            total_credits_topped_up=total_credits,
        ),
    )
