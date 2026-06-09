"""Assign seats to a list of students."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import SeatAssignmentEntry, SeatAssignmentResult
from virtual_labs.domain.project import ProjectCreationBody
from virtual_labs.infrastructure.db.models import Course, CourseStatus, Seat
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.infrastructure.settings import settings
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


async def _transfer_credits(
    virtual_lab_id: UUID4, project_id: UUID4, amount: float
) -> bool:
    """Best-effort assign_project_budget. Returns True on success."""
    if settings.ACCOUNTING_BASE_URL is None:
        return False
    try:
        await accounting_cases.assign_project_budget(
            virtual_lab_id=virtual_lab_id, project_id=project_id, amount=amount
        )
        logger.info(
            f"Transferred {amount} credits to project {project_id} in vlab {virtual_lab_id}"
        )
        return True
    except Exception as ex:  # noqa: BLE001
        logger.error(
            f"Failed to transfer credits to project {project_id} in vlab {virtual_lab_id}: {ex}"
        )
        return False


async def assign_seats(
    db: AsyncSession,
    *,
    course: Course,
    students: list[SeatAssignmentEntry],
    auth: tuple[AuthUserGrants, str],
) -> list[SeatAssignmentResult]:
    """Assign one seat per student: lock seats, create all projects, then best-effort credit transfer.

    Flow:
    1. Pre-checks (course active, not past drop date).
    2. Lock available seats (FOR UPDATE SKIP LOCKED).
    3. Create all projects and assign seats in one batch.
    4. Best-effort budget transfer for each seat — failures are logged and
       reflected in the response but do not roll back the assignment.
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

    # Lock seats up front
    seats = await get_available_seats(db, course.id, len(students))

    # Create all projects and assign seats
    assigned: list[tuple[Seat, SeatAssignmentEntry, UUID4]] = []
    results: list[SeatAssignmentResult] = []

    for seat, student in zip(seats, students):
        try:
            project_out = await create_new_project_use_case(
                db,
                virtual_lab_id=course.virtual_lab_id,
                payload=ProjectCreationBody(
                    name=student.student_id, contact_email=student.email
                ),
                auth=auth,
            )
            seat.active_project_id = project_out.id
            assigned.append((seat, student, project_out.id))
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to create project for {student.student_id}: {ex}")
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=False,
                    credit_transferred=False,
                    error=str(ex),
                )
            )

    # Commit all seat assignments in one operation
    await db.commit()

    # Best-effort budget assignments
    for seat, student, project_id in assigned:
        transferred = await _transfer_credits(
            virtual_lab_id=course.virtual_lab_id,
            project_id=project_id,
            amount=float(seat.credit_value),
        )
        if not transferred:
            logger.warning(
                f"Credit transfer failed for student {student.student_id}, "
                f"project {project_id} — seat assigned but unfunded"
            )

        results.append(
            SeatAssignmentResult(
                student_id=student.student_id,
                email=student.email,
                assignment_successful=True,
                credit_transferred=transferred,
                project_id=project_id,
            )
        )

    return results
