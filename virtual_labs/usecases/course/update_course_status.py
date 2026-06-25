"""Activate or void a course."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.course import CourseOut
from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, Seat
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.course.drop_seats import _drop_single_seat


async def _get_course(db: AsyncSession, course_id: UUID) -> Course:
    """Fetch course by ID or raise 404."""
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message=f"Course {course_id} not found",
        )
    return course


async def activate_course(
    db: AsyncSession,
    course_id: UUID,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Set course status to active. Only draft courses can be activated."""
    course = await _get_course(db, course_id)

    try:
        course.activate()
    except ValueError as e:
        raise VliError(
            error_code=VliErrorCode.NOT_ALLOWED_OP,
            http_status_code=HTTPStatus.CONFLICT,
            message=str(e),
        )

    await db.commit()
    await db.refresh(course)

    logger.info(f"Course {course_id} activated by user {auth[0].sub}")

    return VliAppResponse[CourseOut](
        message="Course activated successfully",
        data=CourseOut.model_validate(course),
    )


async def void_course(
    db: AsyncSession,
    course_id: UUID,
    auth: tuple[AuthUser, str],
) -> VliAppResponse[CourseOut]:
    """Set course status to voided.

    This also drops every undropped enrolment (depleting each project's budget)
    and depletes the virtual-lab budget.
    """
    course = await _get_course(db, course_id)

    course.void()

    # --- Drop all undropped enrolments (deplete project budgets) ---
    result = await db.execute(
        select(Seat.id, CourseEnrolment.id)
        .join(CourseEnrolment, CourseEnrolment.id == Seat.enrolment_id)
        .where(
            Seat.course_id == course.id,
            CourseEnrolment.is_dropped.is_(False),
        )
    )
    work_items: list[tuple[UUID, UUID]] = [(row[0], row[1]) for row in result.all()]

    dropped = 0
    failed = 0
    for seat_id, enrolment_id in work_items:
        seat = await db.get(Seat, seat_id)
        enrolment = await db.get(CourseEnrolment, enrolment_id)
        # Re-fetch course each iteration: _drop_single_seat commits, which
        # expires relationships on the course object (e.g. virtual_lab).
        course = await db.get(Course, course_id)
        if seat is None or enrolment is None or course is None:
            continue
        if enrolment.is_dropped:
            continue
        try:
            await _drop_single_seat(db, seat=seat, enrolment=enrolment, course=course)
            dropped += 1
        except Exception as ex:  # noqa: BLE001
            logger.error(
                f"Failed to drop enrolment {enrolment_id} while voiding "
                f"course {course_id}: {ex}"
            )
            failed += 1

    # --- Deplete vlab budget ---
    course = await db.get(Course, course_id)
    assert course is not None
    if not course.budget_depleted:
        success = await accounting_cases.deplete_vlab_budget(
            virtual_lab_id=course.virtual_lab_id,
        )
        if success is None:
            logger.error(
                f"Failed to deplete vlab budget for course {course_id} during void"
            )
        else:
            course.budget_depleted = True

    await db.commit()
    await db.refresh(course)

    logger.info(
        f"Course {course_id} voided by user {auth[0].sub} "
        f"(enrolments dropped={dropped}, failed={failed}, "
        f"budget_depleted={course.budget_depleted})"
    )

    return VliAppResponse[CourseOut](
        message="Course voided successfully",
        data=CourseOut.model_validate(course),
    )
