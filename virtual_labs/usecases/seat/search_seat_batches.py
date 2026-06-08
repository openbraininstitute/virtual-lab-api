"""Search seat batches with filtering."""

from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from itertools import groupby
from operator import attrgetter
from typing import Optional

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.seat import (
    CourseSummary,
    InstitutionSummary,
    SeatBatchOut,
    SeatBatchSearchResponse,
    SeatOut,
)
from virtual_labs.infrastructure.db.models import Course, Institution, Seat, VirtualLab


async def get_seat_batch_by_id(
    db: AsyncSession,
    batch_id: UUID4,
) -> VliAppResponse[SeatBatchSearchResponse]:
    """Get a specific batch of seats by batch_id."""
    result = await db.execute(
        select(Seat)
        .where(Seat.batch_id == batch_id)
        .options(joinedload(Seat.course).joinedload(Course.virtual_lab))
        .options(joinedload(Seat.institution))
        .order_by(Seat.created_at)
    )
    seats = result.scalars().unique().all()

    if not seats:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Seat batch {batch_id} not found",
        )

    first_seat = seats[0]
    course = first_seat.course
    institution = first_seat.institution

    institution_summary = InstitutionSummary.model_validate(institution)
    course_summary = CourseSummary(
        id=course.id,
        virtual_lab_id=course.virtual_lab_id,
        virtual_lab_name=course.virtual_lab.name,
        institution_id=course.institution_id,
        template_project_id=course.template_project_id,
        status=course.status.value,
        start_date=course.start_date,
        end_date=course.end_date,
    )

    seat_outputs = [SeatOut.model_validate(s) for s in seats]
    batch = SeatBatchOut(
        batch_id=first_seat.batch_id,
        created_at=first_seat.created_at,
        expiry_date=first_seat.expiry_date,
        number_of_seats=len(seat_outputs),
        seats=seat_outputs,
    )

    return VliAppResponse(
        message="Seat batch found",
        data=SeatBatchSearchResponse(
            institution=institution_summary,
            course=course_summary,
            batches=[batch],
        ),
    )


async def search_seat_batches(
    db: AsyncSession,
    *,
    course_id: Optional[UUID4] = None,
    institution_id: Optional[UUID4] = None,
    vlab_name: Optional[str] = None,
    institution_name: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
) -> VliAppResponse[SeatBatchSearchResponse]:
    """Search seat batches with optional filters."""
    query = (
        select(Seat)
        .join(Course, Seat.course_id == Course.id)
        .join(VirtualLab, Course.virtual_lab_id == VirtualLab.id)
        .join(Institution, Seat.institution_id == Institution.id)
        .options(joinedload(Seat.course).joinedload(Course.virtual_lab))
        .options(joinedload(Seat.institution))
    )

    if course_id is not None:
        query = query.where(Seat.course_id == course_id)
    if institution_id is not None:
        query = query.where(Seat.institution_id == institution_id)
    if vlab_name is not None:
        query = query.where(VirtualLab.name.ilike(f"%{vlab_name}%"))
    if institution_name is not None:
        query = query.where(Institution.name.ilike(f"%{institution_name}%"))
    if created_after is not None:
        query = query.where(Seat.created_at >= created_after)
    if created_before is not None:
        query = query.where(Seat.created_at <= created_before)

    query = query.order_by(Seat.batch_id, Seat.created_at)

    result = await db.execute(query)
    seats = result.scalars().unique().all()

    if not seats:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="No seat batches found matching the given filters",
        )

    # All seats in the result share the same course & institution (via filters)
    # but to be safe, group by batch_id and use the first seat's relations
    first_seat = seats[0]
    course = first_seat.course
    institution = first_seat.institution

    institution_summary = InstitutionSummary.model_validate(institution)
    course_summary = CourseSummary(
        id=course.id,
        virtual_lab_id=course.virtual_lab_id,
        virtual_lab_name=course.virtual_lab.name,
        institution_id=course.institution_id,
        template_project_id=course.template_project_id,
        status=course.status.value,
        start_date=course.start_date,
        end_date=course.end_date,
    )

    # Group seats by batch_id
    batches: list[SeatBatchOut] = []
    for bid, group in groupby(seats, key=attrgetter("batch_id")):
        batch_seats = list(group)
        seat_outputs = [SeatOut.model_validate(s) for s in batch_seats]
        batches.append(
            SeatBatchOut(
                batch_id=bid,
                created_at=batch_seats[0].created_at,
                expiry_date=batch_seats[0].expiry_date,
                number_of_seats=len(seat_outputs),
                seats=seat_outputs,
            )
        )

    return VliAppResponse(
        message=f"Found {len(batches)} seat batch(es)",
        data=SeatBatchSearchResponse(
            institution=institution_summary,
            course=course_summary,
            batches=batches,
        ),
    )
