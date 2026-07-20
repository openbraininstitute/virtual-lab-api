from http import HTTPStatus
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.types import VliAppResponse
from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, CourseStatus, Seat
from virtual_labs.usecases import accounting as accounting_cases
from virtual_labs.usecases.course.drop_seats import _drop_single_seat
from virtual_labs.usecases.course.update_course_status import _get_course


async def delete_course(
    db: AsyncSession,
    course_id: UUID,
) -> VliAppResponse[None]:
    """Drop all students, deplete budgets, then hard-delete the course and its seats.

    Raises on any failure — course isn't deleted unless everything succeeds.
    """
    course = await _get_course(db, course_id)

    if course.status == CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.FORBIDDEN_OPERATION,
            http_status_code=HTTPStatus.CONFLICT,
            message="Active courses cannot be deleted. Void the course first.",
        )

    course.void()

    # Lock all seats for this course upfront — blocks concurrent assign_seats
    await db.execute(select(Seat).where(Seat.course_id == course_id).with_for_update())

    # Drop all undropped enrolments — strict: any failure aborts the whole operation
    result = await db.execute(
        select(Seat.id, CourseEnrolment.id)
        .join(CourseEnrolment, CourseEnrolment.id == Seat.enrolment_id)
        .where(
            Seat.course_id == course_id,
            CourseEnrolment.is_dropped.is_(False),
        )
    )
    work_items: list[tuple[UUID, UUID]] = [(row[0], row[1]) for row in result.all()]

    for seat_id, enrolment_id in work_items:
        seat = await db.get(Seat, seat_id)
        enrolment = await db.get(CourseEnrolment, enrolment_id)
        course = await db.get(Course, course_id)
        if seat is None or enrolment is None or course is None:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                message=f"Seat or enrolment disappeared mid-delete for course {course_id}",
            )
        async with db.begin_nested():
            await _drop_single_seat(
                db, seat=seat, enrolment=enrolment, course=course, commit=False
            )

    # Deplete vlab budget — strict: failure aborts
    course = await db.get(Course, course_id)
    assert course is not None
    if not course.budget_depleted:
        success = await accounting_cases.deplete_vlab_budget(
            virtual_lab_id=course.virtual_lab_id,
        )
        if success is None:
            raise VliError(
                error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
                http_status_code=HTTPStatus.BAD_GATEWAY,
                message=f"Failed to deplete vlab budget for course {course_id}",
            )
        course.budget_depleted = True

    # Hard-delete: seats first (FK → enrolment), then enrolments, then course
    enrolment_ids = (
        (
            await db.execute(
                select(CourseEnrolment.id).where(CourseEnrolment.course_id == course_id)
            )
        )
        .scalars()
        .all()
    )

    await db.execute(delete(Seat).where(Seat.course_id == course_id))
    if enrolment_ids:
        await db.execute(
            delete(CourseEnrolment).where(CourseEnrolment.id.in_(enrolment_ids))
        )
    await db.execute(delete(Course).where(Course.id == course_id))
    await db.commit()

    return VliAppResponse[None](message="Course deleted successfully", data=None)
