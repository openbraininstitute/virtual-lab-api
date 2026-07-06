"""Daily cron: drop enrolments in expired courses, then deplete vlab budgets.

Two independent steps:
1. drop_expired_enrolments — drop all undropped enrolments in courses past end_date.
2. deplete_expired_courses — deplete vlab budget for courses with no remaining enrolments.

expire_courses runs both in sequence.
"""

from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    Course,
    CourseEnrolment,
    CourseStatus,
    Seat,
)
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.course.drop_seats import _drop_single_seat


async def drop_expired_enrolments(db: AsyncSession) -> dict:
    """Drop all undropped enrolments in courses past end_date or voided."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Seat.id, CourseEnrolment.id, Course.id)
        .join(CourseEnrolment, CourseEnrolment.id == Seat.enrolment_id)
        .join(Course, Course.id == CourseEnrolment.course_id)
        .where(
            or_(
                # Expired: past end_date
                (Course.end_date.is_not(None)) & (Course.end_date < now),
                # Voided: dates don't matter
                Course.status == CourseStatus.VOIDED,
            ),
            CourseEnrolment.is_dropped.is_(False),
        )
    )
    work_items: list[tuple[UUID, UUID, UUID]] = [
        (row[0], row[1], row[2]) for row in result.all()
    ]

    if not work_items:
        return {"enrolments_dropped": 0, "enrolments_failed": 0}

    total_dropped = 0
    total_failed = 0

    for seat_id, enrolment_id, course_id in work_items:
        seat = await db.get(Seat, seat_id)
        enrolment = await db.get(CourseEnrolment, enrolment_id)
        course = await db.get(Course, course_id)

        if seat is None or enrolment is None or course is None:
            continue

        if enrolment.is_dropped:
            continue

        try:
            await _drop_single_seat(db, seat=seat, enrolment=enrolment, course=course)
            total_dropped += 1
        except Exception as ex:  # noqa: BLE001
            logger.error(
                f"Failed to drop enrolment {enrolment_id} in expired "
                f"course {course_id}: {ex}"
            )
            total_failed += 1

    return {"enrolments_dropped": total_dropped, "enrolments_failed": total_failed}


async def deplete_expired_courses(db: AsyncSession) -> dict:
    """Deplete vlab budget for expired or voided courses."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Course.id).where(
            or_(
                # Expired: past end_date
                (Course.end_date.is_not(None)) & (Course.end_date < now),
                # Voided: dates don't matter
                Course.status == CourseStatus.VOIDED,
            ),
            Course.budget_depleted.is_(False),
        )
    )
    candidate_ids: list[UUID] = [row[0] for row in result.all()]

    if not candidate_ids:
        return {"vlabs_depleted": 0}

    vlabs_depleted = 0

    for course_id in candidate_ids:
        course = await db.get(Course, course_id)
        if course is None or course.budget_depleted:
            continue

        success = await accounting_cases.deplete_vlab_budget(
            virtual_lab_id=course.virtual_lab_id,
        )
        if success is None:
            logger.error(f"Failed to deplete vlab budget for course {course_id}")
            continue

        course.budget_depleted = True
        await db.commit()
        vlabs_depleted += 1
        logger.info(f"Depleted vlab budget for expired course {course_id}")

    return {"vlabs_depleted": vlabs_depleted}


async def expire_courses(db: AsyncSession) -> dict:
    """Run both steps: drop enrolments, then deplete budgets."""
    drop_result = await drop_expired_enrolments(db)
    deplete_result = await deplete_expired_courses(db)

    return {
        "expired_courses_found": (
            1
            if drop_result["enrolments_dropped"] > 0
            or deplete_result["vlabs_depleted"] > 0
            else 0
        ),
        "enrolments_dropped": drop_result["enrolments_dropped"],
        "enrolments_failed": drop_result["enrolments_failed"],
        "vlabs_depleted": deplete_result["vlabs_depleted"],
    }
