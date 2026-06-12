"""Assign seats to a list of students."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import SeatAssignmentEntry, SeatAssignmentResult
from virtual_labs.domain.project import ProjectCreationBody
from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.db.models import (
    Course,
    CourseEnrolment,
    CourseStatus,
    Project,
    Seat,
)
from virtual_labs.infrastructure.email.send_enrolment_claim_email import (
    EnrolmentClaimEmailDetails,
    send_enrolment_claim_email,
)
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.project.create_new_project import create_new_project_use_case


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
    auth: tuple[AuthUserGrants, str],
) -> list[SeatAssignmentResult]:
    """Assign one seat per student: create project, fund it, create enrolment, send claim email.

    Flow:
    1. Pre-checks (course active, not past drop date).
    2. Check no duplicate enrolments for the given emails/student_ids.
    3. Lock available seats (FOR UPDATE SKIP LOCKED).
    4. For each student: create project, fund it, create enrolment, link seat.
       If funding fails → soft-delete project, report error.
    5. Send claim emails (best-effort).
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

    course_id = course.id
    virtual_lab_id = course.virtual_lab_id
    course_name = course.virtual_lab.name
    credit_per_seat = float(course.credits_per_seat)
    seat_ids = [s.id for s in seats]

    # Create projects, enrolments, and assign seats.
    # create_new_project_use_case issues a session.rollback() internally,
    # so we process each student individually.
    results: list[SeatAssignmentResult] = []

    for seat, student, seat_id in zip(seats, students, seat_ids):
        project_id = None
        try:
            # Use a dedicated session for project creation so the rollback
            # inside create_new_project_use_case doesn't release the FOR UPDATE
            # locks held by the outer session on the seats.
            async with session_pool.session() as project_session:
                project_out = await create_new_project_use_case(
                    project_session,
                    virtual_lab_id=virtual_lab_id,
                    payload=ProjectCreationBody(
                        name=student.student_id,
                    ),
                    auth=auth,
                )
            project_id = project_out.id

            # Fund the project — must succeed before we assign the seat
            funded = await accounting_cases.fund_project(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                amount=credit_per_seat,
            )
            if not funded:
                raise RuntimeError("Failed to fund project")

            # Create enrolment linked to the project
            enrolment = CourseEnrolment(
                course_id=course_id,
                contact_email=student.email,
                student_id=student.student_id,
                project_id=project_id,
            )
            db.add(enrolment)
            await db.flush()

            # Capture the generated id before it gets expired
            enrolment_id = enrolment.id

            # Link seat to enrolment
            seat.enrolment_id = enrolment_id
            await db.commit()

            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=True,
                    seat_id=seat_id,
                    enrolment_id=enrolment_id,
                    project_id=project_id,
                    credit_transferred_amount=credit_per_seat,
                )
            )
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to assign seat for {student.student_id}: {ex}")
            # Soft-delete the orphan project if it was already created
            if project_id is not None:
                try:
                    await db.execute(
                        update(Project)
                        .where(Project.id == project_id)
                        .values(deleted=True)
                    )
                    await db.commit()
                    logger.info(
                        f"Soft-deleted orphan project {project_id} for {student.student_id}"
                    )
                except Exception as cleanup_ex:  # noqa: BLE001
                    logger.error(
                        f"Failed to soft-delete orphan project {project_id}: {cleanup_ex}"
                    )
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=False,
                    seat_id=seat_id,
                    error=str(ex),
                )
            )

    # Best-effort: send claim emails after all assignments
    for result in results:
        if not result.assignment_successful or result.enrolment_id is None:
            continue
        try:
            await send_enrolment_claim_email(
                EnrolmentClaimEmailDetails(
                    recipient_email=result.email,
                    enrolment_id=result.enrolment_id,
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
