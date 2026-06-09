"""Assign seats to a list of students."""

import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import SeatAssignmentEntry, SeatAssignmentResult
from virtual_labs.domain.project import ProjectCreationBody
from virtual_labs.infrastructure.db.models import Course, CourseStatus, Project, Seat
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


async def _get_vlab_balance(virtual_lab_id: UUID4) -> float | None:
    """Return current vlab balance or None if accounting is unavailable."""
    if settings.ACCOUNTING_BASE_URL is None:
        return None
    try:
        resp = await accounting_cases.get_virtual_lab_balance(
            virtual_lab_id=virtual_lab_id, include_projects=False
        )
        return float(resp.data.balance)
    except Exception as ex:  # noqa: BLE001
        logger.error(f"Failed to fetch balance for vlab {virtual_lab_id}: {ex}")
        return None


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

    # Capture values before create_new_project_use_case expires the session
    virtual_lab_id = course.virtual_lab_id
    seat_credits = [float(s.credit_value) for s in seats]
    seat_ids = [s.id for s in seats]

    # Create projects and assign seats — commit each individually because
    # create_new_project_use_case issues a session.rollback() internally.
    assigned: list[tuple[SeatAssignmentEntry, UUID4, float, UUID4]] = []
    results: list[SeatAssignmentResult] = []

    for seat, student, seat_credit, seat_id in zip(
        seats, students, seat_credits, seat_ids
    ):
        project_id = None
        try:
            project_out = await create_new_project_use_case(
                db,
                virtual_lab_id=virtual_lab_id,
                payload=ProjectCreationBody(
                    name=student.student_id, contact_email=student.email
                ),
                auth=auth,
            )
            project_id = project_out.id
            seat.active_project_id = project_out.id
            await db.commit()
            assigned.append((student, project_out.id, seat_credit, seat_id))
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to assign seat for {student.student_id}: {ex}")
            # Soft-delete the orphan project if it was already created
            if project_id is not None:
                try:
                    await db.execute(
                        update(Project)
                        .where(Project.id == project_id)
                        .values(deleted=True, contact_email=None)
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
                    credit_transferred=False,
                    seat_id=seat_id,
                    error=str(ex),
                )
            )

    # Best-effort budget assignments — check balance before each transfer
    for student, project_id, seat_credit, seat_id in assigned:
        # Allow accounting service to settle previous transfer
        await asyncio.sleep(0.2)

        balance = await _get_vlab_balance(virtual_lab_id)

        if balance is None:
            # Accounting unavailable — can't transfer
            logger.warning(
                f"Accounting unavailable for student {student.student_id}, "
                f"project {project_id} — seat assigned but unfunded"
            )
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=True,
                    credit_transferred=False,
                    credit_transferred_amount=None,
                    seat_id=seat_id,
                    project_id=project_id,
                )
            )
            continue

        if balance <= 0:
            # No credits left — skip transfer
            logger.warning(
                f"No balance remaining for student {student.student_id}, "
                f"project {project_id} — seat assigned but unfunded"
            )
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=True,
                    credit_transferred=False,
                    credit_transferred_amount=0,
                    seat_id=seat_id,
                    project_id=project_id,
                )
            )
            continue

        # Determine transfer amount: full seat credit or whatever remains
        transfer_amount = min(seat_credit, balance)
        partial = transfer_amount < seat_credit

        transferred = await _transfer_credits(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=transfer_amount,
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
                    credit_transferred=False,
                    credit_transferred_amount=0,
                    seat_id=seat_id,
                    project_id=project_id,
                )
            )
        elif partial:
            logger.warning(
                f"Partial credit for student {student.student_id}, "
                f"project {project_id}: transferred {transfer_amount}/{seat_credit}"
            )
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=True,
                    credit_transferred=True,
                    credit_transferred_amount=transfer_amount,
                    seat_id=seat_id,
                    project_id=project_id,
                    error=f"Partial credit: {transfer_amount}/{seat_credit}",
                )
            )
        else:
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=True,
                    credit_transferred=True,
                    credit_transferred_amount=transfer_amount,
                    seat_id=seat_id,
                    project_id=project_id,
                )
            )

    return results
