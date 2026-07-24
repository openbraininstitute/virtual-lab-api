"""Assign seats to a list of students."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID, uuid4

from loguru import logger
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import Ledger, ledger_container
from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.course import SeatAssignmentEntry, SeatAssignmentResult
from virtual_labs.domain.project import ProjectCreationBody
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
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.infrastructure.kc.grant import AuthUserGrants
from virtual_labs.infrastructure.kc.models import CreatedGroup
from virtual_labs.shared.group_namespace import make_project_group_name
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.project.create_new_project import (
    _make_deplete_compensation,
    _make_kc_group_compensation,
    create_project_record,
    ensure_accounting_initialization,
    ensure_group_creation,
    ensure_unique_name_within_virtual_lab,
    ensure_virtual_lab_exists,
)


async def _create_waitlisted_group(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    course: Course,
    comp: Ledger,
) -> str | None:
    """Create the waitlisted KC group if the course hasn't started yet.

    Returns the waitlisted_group_id, or None if the course has already started.
    User membership is handled later at claim time.
    """
    now = datetime.now(timezone.utc)
    course_started = course.start_date is None or now >= course.start_date.replace(
        tzinfo=timezone.utc
    )
    if course_started:
        return None

    waitlisted_group_name = make_project_group_name(
        virtual_lab_id, project_id, UserRoleEnum.waitlisted
    )
    wg_id = await KeycloakRealm.a_create_group({"name": waitlisted_group_name})
    assert wg_id is not None
    waitlisted_group: CreatedGroup = {"id": wg_id, "name": waitlisted_group_name}
    comp.push(await _make_kc_group_compensation(waitlisted_group))
    return wg_id


async def _assign_seat(
    session: AsyncSession,
    *,
    virtual_lab_id: UUID4,
    course: Course,
    student_email: str,
    student_id: str,
    seat: Seat,
    payload: ProjectCreationBody,
    auth: tuple[AuthUserGrants, str],
) -> SeatAssignmentResult:
    """Assign a single seat to a student.

    Orchestrates the full seat-assignment flow for one student:
    1. Creates a dedicated project inside the virtual lab.
    2. Initialises the project's accounting ledger.
    3. Funds the project with the course's credits_per_seat.
    4. Creates a CourseEnrolment record linking the student to the project.
    5. Links the seat to the enrolment.

    All steps run inside a compensation ledger; if any step fails, previous
    side-effects (KC groups, accounting top-up) are automatically rolled back.
    """
    user_id = auth[0].id
    await ensure_unique_name_within_virtual_lab(
        session,
        virtual_lab_id=virtual_lab_id,
        project_name=payload.name,
    )

    virtual_lab = await ensure_virtual_lab_exists(
        session,
        virtual_lab_id=virtual_lab_id,
    )
    project_draft_id: UUID4 = uuid4()

    vlab_admin_group_id = str(virtual_lab.admin_group_id)
    vlab_member_group_id = str(virtual_lab.member_group_id)
    await session.refresh(virtual_lab, ["course"])
    is_course_vlab = bool(virtual_lab.course)
    assert is_course_vlab
    credits_per_seat = virtual_lab.course.credits_per_seat

    async with ledger_container() as comp:
        admin_group, member_group, _ = await ensure_group_creation(
            vlab_admin_group_id=vlab_admin_group_id,
            vlab_member_group_id=vlab_member_group_id,
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            user_id=user_id,
            comp=comp,
        )

        waitlisted_group_id = await _create_waitlisted_group(
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            course=course,
            comp=comp,
        )

        await ensure_accounting_initialization(
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            project_name=payload.name,
            comp=comp,
        )

        await create_project_record(
            session,
            project_id=project_draft_id,
            virtual_lab_id=virtual_lab_id,
            payload=payload,
            admin_group=admin_group,
            member_group=member_group,
            waitlisted_group_id=waitlisted_group_id,
            user_id=user_id,
            commit=False,
        )

        funded = await accounting_cases.fund_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_draft_id,
            amount=float(credits_per_seat),
        )
        if not funded:
            raise RuntimeError("Failed to fund project")

        comp.push(_make_deplete_compensation(virtual_lab_id, project_draft_id))

        enrolment = CourseEnrolment(
            course_id=course.id,
            contact_email=student_email,
            student_id=student_id,
            project_id=project_draft_id,
        )
        session.add(enrolment)
        await session.flush()

        enrolment_id = enrolment.id
        seat.enrolment_id = enrolment_id

        return SeatAssignmentResult(
            student_id=student_id,
            email=student_email,
            assignment_successful=True,
            seat_id=seat.id,
            enrolment_id=enrolment_id,
            project_id=project_draft_id,
            credit_transferred_amount=float(credits_per_seat),
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

    virtual_lab_id = course.virtual_lab_id
    course_name = course.virtual_lab.name

    # Create projects, enrolments, and assign seats.
    results: list[SeatAssignmentResult] = []

    for seat, student in zip(seats, students):
        try:
            async with db.begin_nested():
                result = await _assign_seat(
                    db,
                    virtual_lab_id=virtual_lab_id,
                    course=course,
                    student_email=student.email,
                    student_id=student.student_id,
                    seat=seat,
                    payload=ProjectCreationBody(
                        name=student.student_id,
                    ),
                    auth=auth,
                )

            results.append(result)
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to assign seat for {student.student_id}: {ex}")
            results.append(
                SeatAssignmentResult(
                    student_id=student.student_id,
                    email=student.email,
                    assignment_successful=False,
                    seat_id=seat.id,
                    error=str(ex),
                )
            )

    # Single commit at the end — keeps FOR UPDATE locks held for the
    # entire batch, preventing concurrent requests from stealing seats.
    await db.commit()

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
