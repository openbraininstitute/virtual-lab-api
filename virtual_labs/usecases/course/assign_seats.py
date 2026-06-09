"""Assign seats to a list of users (by email).

For each email, finds an available (unconsumed, unexpired) seat for the course,
creates a new project in the virtual lab, and links the seat to that project.
"""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import SeatAssignmentEntry
from virtual_labs.domain.project import ProjectCreationBody
from virtual_labs.domain.seat import SeatOut
from virtual_labs.infrastructure.db.models import Course, CourseStatus, Seat
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.usecases.project.create_new_project import (
    create_new_project_use_case,
)


async def get_available_seats(
    db: AsyncSession, course_id: UUID, count: int
) -> list[Seat]:
    """Return `count` unconsumed, unexpired seats for the given course.

    Uses FOR UPDATE SKIP LOCKED so concurrent callers never claim the
    same row.  Raises VliError if fewer than `count` seats are available.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Seat)
        .where(
            Seat.course_id == course_id,
            Seat.is_consumed.is_(False),
            Seat.active_project_id.is_(None),
            Seat.expiry_date > now,
        )
        .order_by(Seat.expiry_date.asc())
        .limit(count)
        .with_for_update(skip_locked=True)
    )
    seats = result.scalars().all()
    if len(seats) < count:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Not enough available seats: requested {count}, found {len(seats)}",
        )
    return list(seats)


async def assign_seats(
    db: AsyncSession,
    *,
    course: Course,
    students: list[SeatAssignmentEntry],
    auth: tuple[AuthUserGrants, str],
) -> list[SeatOut]:
    """Assign one seat per student: create a project and mark the seat consumed."""

    # 0. Ensure course is active and we're before the last drop date
    if course.status != CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Cannot assign seats: course is in '{course.status.value}' status",
        )

    now = datetime.now(timezone.utc)
    if course.last_drop_date is not None and now >= course.last_drop_date:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Cannot assign seats after the course last drop date",
        )

    # 1. Lock the required number of seats up front
    seats = await get_available_seats(db, course.id, len(students))

    for seat, student in zip(seats, students):
        # 2. Create a new project in the course's virtual lab
        project_out = await create_new_project_use_case(
            db,
            virtual_lab_id=course.virtual_lab_id,
            payload=ProjectCreationBody(
                name=f"seat-{seat.id}",
                contact_email=student.email,
            ),
            auth=auth,
        )

        # 3. Link the seat to the new project
        seat.active_project_id = project_out.id

    await db.commit()
    for seat in seats:
        await db.refresh(seat)

    return [SeatOut.model_validate(s) for s in seats]
