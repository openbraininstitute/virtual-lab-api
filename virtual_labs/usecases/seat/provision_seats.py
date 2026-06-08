"""Provision seats for a virtual lab.

Creates the requested number of seat records and tops up the virtual lab
budget via the accounting service.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import ProvisionSeatsBody, ProvisionSeatsResponse, SeatOut
from virtual_labs.infrastructure.db.models import Seat
from virtual_labs.infrastructure.settings import settings
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.labs.get_virtual_lab_or_raise import (
    get_virtual_lab_or_raise,
)


async def provision_seats(
    db: AsyncSession,
    payload: ProvisionSeatsBody,
) -> VliAppResponse[ProvisionSeatsResponse]:
    # 1. Validate virtual lab exists and is not deleted
    vlab = await get_virtual_lab_or_raise(db, payload.virtual_lab_id)

    # 2. Check that the virtual lab has an associated course
    if not vlab.course:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.BAD_REQUEST,
            message="Virtual lab does not have an associated course",
        )

    # 3. Create seat records
    batch_id = uuid.uuid4()
    expiry_date = datetime.now(timezone.utc) + timedelta(days=settings.SEAT_EXPIRY_DAYS)
    seats: list[Seat] = []
    for _ in range(payload.number_of_seats):
        seat = Seat(
            virtual_lab_id=payload.virtual_lab_id,
            institution_id=vlab.course.institution_id,
            batch_id=batch_id,
            expiry_date=expiry_date,
        )
        db.add(seat)
        seats.append(seat)

    await db.flush()

    # 4. Top up the virtual lab budget
    total_credits = payload.number_of_seats * settings.CREDITS_PER_SEAT

    if settings.ACCOUNTING_BASE_URL is not None:
        try:
            await accounting_cases.top_up_virtual_lab_budget(
                virtual_lab_id=payload.virtual_lab_id,
                amount=total_credits,
            )
            logger.info(
                f"Topped up vlab {payload.virtual_lab_id} with {total_credits} credits "
                f"for {payload.number_of_seats} seats"
            )
        except Exception as ex:
            logger.error(
                f"Failed to top up vlab {payload.virtual_lab_id} "
                f"for seat provisioning: {ex}"
            )
            raise VliError(
                error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
                http_status_code=HTTPStatus.BAD_GATEWAY,
                message="Failed to top up virtual lab budget via accounting service",
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
