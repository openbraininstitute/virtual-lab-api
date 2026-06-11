"""Daily cron: drop all enrolments in courses that have ended.

Single-pass logic:
1. SELECT seats joined to undropped enrolments in active courses WHERE end_date < now.
2. Run the existing _drop_single_seat flow for each.
3. Failed drops stay is_dropped = False → next run retries automatically.
4. Idempotent — safe to re-run.
"""

from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    Course,
    CourseEnrolment,
    Seat,
)
from virtual_labs.usecases.course.drop_seats import _drop_single_seat


async def expire_courses(db: AsyncSession) -> dict:
    """Process all expired active courses: drop their undropped enrolments.

    Returns a summary dict with counts.
    """
    now = datetime.now(timezone.utc)

    # Single query: seats linked to undropped enrolments in expired active courses
    result = await db.execute(
        select(Seat.id, CourseEnrolment.id, Course.id)
        .join(CourseEnrolment, CourseEnrolment.id == Seat.enrolment_id)
        .join(Course, Course.id == CourseEnrolment.course_id)
        .where(
            Course.end_date.is_not(None),
            Course.end_date < now,
            CourseEnrolment.is_dropped.is_(False),
        )
    )
    work_items: list[tuple[UUID, UUID, UUID]] = [
        (row[0], row[1], row[2]) for row in result.all()
    ]

    if not work_items:
        summary = {
            "expired_courses_found": 0,
            "courses_with_active_enrolments": 0,
            "enrolments_dropped": 0,
            "enrolments_failed": 0,
        }
        logger.info(f"expire_courses completed: {summary}")
        return summary

    total_dropped = 0
    total_failed = 0
    course_ids: set[UUID] = set()

    for seat_id, enrolment_id, course_id in work_items:
        course_ids.add(course_id)

        # Re-fetch fresh objects (previous _drop_single_seat commits expire them)
        seat = await db.get(Seat, seat_id)
        enrolment = await db.get(CourseEnrolment, enrolment_id)
        course = await db.get(Course, course_id)

        if seat is None or enrolment is None or course is None:
            continue

        if enrolment.is_dropped:
            # Already handled (e.g. by a concurrent run)
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

    summary = {
        "expired_courses_found": len(course_ids),
        "courses_with_active_enrolments": len(course_ids),
        "enrolments_dropped": total_dropped,
        "enrolments_failed": total_failed,
    }

    logger.info(f"expire_courses completed: {summary}")
    return summary
