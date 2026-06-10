"""Assign seats to a list of students."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import SeatAssignmentEntry, SeatAssignmentResult
from virtual_labs.infrastructure.db.models import (
    Course,
    CourseEnrolment,
    CourseStatus,
    Seat,
)
from virtual_labs.infrastructure.email.send_enrolment_claim_email import (
    EnrolmentClaimEmailDetails,
    send_enrolment_claim_email,
)


async def get_available_seats(
    db: AsyncSession, course_id: UUID, count: int
) -> list[Seat]:
    """Return `count` unconsumed, unexpired seats. Uses FOR UPDATE SKIP LOCKED."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Seat)
        .where(
            Seat.course_id == course_id,
            Seat.is_consumed.is_(False),
            Seat.enrolment_id.is_(None),
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


async def _check_duplicate_enrolments(
    db: AsyncSession, course_id: UUID, students: list[SeatAssignmentEntry]
) -> None:
    """Raise if any email or student_id already has an enrolment (active or dropped) in this course."""
    emails = [s.email for s in students]
    student_ids = [s.student_id for s in students]

    result = await db.execute(
        select(CourseEnrolment.contact_email, CourseEnrolment.student_id).where(
            CourseEnrolment.course_id == course_id,
            (CourseEnrolment.contact_email.in_(emails))
            | (CourseEnrolment.student_id.in_(student_ids)),
        )
    )
    existing = result.all()
    if existing:
        dupes = [f"{row.student_id} ({row.contact_email})" for row in existing]
        raise VliError(
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Students already enrolled in this course: {', '.join(dupes)}",
        )


async def assign_seats(
    db: AsyncSession,
    *,
    course: Course,
    students: list[SeatAssignmentEntry],
) -> list[SeatAssignmentResult]:
    """Assign one seat per student: lock seats, create enrolments, send claim emails.

    Flow:
    1. Pre-checks (course active, not past drop date).
    2. Check no duplicate enrolments for the given emails.
    3. Lock available seats (FOR UPDATE SKIP LOCKED).
    4. Create a CourseEnrolment per student and link to the seat.
    5. Send claim email (best-effort) to each student.
    """
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

    # Check for duplicate enrolments
    await _check_duplicate_enrolments(db, course.id, students)

    # Lock seats up front
    seats = await get_available_seats(db, course.id, len(students))

    # Create enrolments and link to seats
    results: list[SeatAssignmentResult] = []

    for seat, student in zip(seats, students):
        enrolment = CourseEnrolment(
            course_id=course.id,
            contact_email=student.email,
            student_id=student.student_id,
        )
        db.add(enrolment)
        await db.flush()  # generate enrolment.id

        seat.enrolment_id = enrolment.id

        results.append(
            SeatAssignmentResult(
                student_id=student.student_id,
                email=student.email,
                seat_id=seat.id,
                enrolment_id=enrolment.id,
            )
        )

    await db.commit()

    # Best-effort: send claim emails after commit (failures don't roll back assignment)
    course_name = course.virtual_lab.name
    for result in results:
        try:
            await send_enrolment_claim_email(
                EnrolmentClaimEmailDetails(
                    recipient_email=result.email,
                    enrolment_id=result.enrolment_id,  # type: ignore[arg-type]
                    course_name=course_name,
                )
            )
        except Exception as ex:  # noqa: BLE001
            result.email_sent = False
            logger.warning(
                f"Failed to send claim email to {result.email} "
                f"(enrolment_id={result.enrolment_id}): {ex}"
            )

    return results
