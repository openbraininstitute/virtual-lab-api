"""Drop (release) seats for students in a course.

- On drop, the project's credits are depleted.
- A seat can only be recovered once:
  - Early drop: marked previously_dropped, released for reassignment.
    If already previously_dropped → consumed.
  - Late drop: consumed.
- If the student has < CREDITS_PER_SEAT - 50 remaining, seat is consumed regardless.
"""

from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.domain.course import DropSeatsBody, SeatDropResult
from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, Project, Seat
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.usecases import accounting as accounting_cases

_MIN_RECOVERABLE_BALANCE = settings.CREDITS_PER_SEAT - 50


async def _remove_all_users_from_group(group_id: str) -> list[str]:
    gqr = GroupQueryRepository()
    umr = UserMutationRepository()

    failed_user_ids: list[str] = []
    users = await gqr.a_retrieve_group_users(group_id=group_id)
    for user in users:
        try:
            await umr.a_detach_user_from_group(user_id=UUID(user.id), group_id=group_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning(
                f"Failed to remove user {user.id} from group {group_id}: {ex}"
            )
            failed_user_ids.append(user.id)
    return failed_user_ids


async def _clear_project_groups(project: Project) -> None:
    failed = await _remove_all_users_from_group(project.member_group_id)
    if failed:
        raise RuntimeError(
            f"Failed to remove {len(failed)} user(s) from project member group: {failed}"
        )


async def _get_project_balance(project_id: UUID) -> float | None:
    if settings.ACCOUNTING_BASE_URL is None:
        return None
    try:
        resp = await accounting_cases.get_project_balance(project_id)
        return float(resp.data.balance)
    except Exception as ex:  # noqa: BLE001
        logger.error(f"Failed to get balance for project {project_id}: {ex}")
        return None


async def drop_seats(
    db: AsyncSession,
    *,
    course: Course,
    payload: DropSeatsBody,
) -> list[SeatDropResult]:
    seat_ids = list(payload.seat_ids)
    result = await db.execute(
        select(Seat)
        .outerjoin(CourseEnrolment, CourseEnrolment.id == Seat.enrolment_id)
        .options(joinedload(Seat.enrolment))
        .where(Seat.id.in_(seat_ids), Seat.course_id == course.id)
    )
    found_seats = {s.id: s for s in result.scalars().unique().all()}

    seats_to_drop: list[tuple[UUID, UUID]] = []
    results: list[SeatDropResult] = []

    for seat_id in seat_ids:
        seat = found_seats.get(seat_id)
        if seat is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Seat not found in this course",
                )
            )
            continue
        if seat.enrolment_id is None or seat.enrolment is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Seat has no enrolment",
                )
            )
            continue
        if seat.enrolment.is_dropped:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Enrolment is already dropped",
                )
            )
            continue
        seats_to_drop.append((seat.id, seat.enrolment.id))

    course_id = course.id
    for seat_id, enrolment_id in seats_to_drop:
        seat = await db.get(Seat, seat_id)
        enrolment = await db.get(CourseEnrolment, enrolment_id)
        course_obj: Course | None = await db.get(Course, course_id)
        if seat is None or enrolment is None or course_obj is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id, drop_successful=False, error="Not found"
                )
            )
            continue
        try:
            await _drop_single_seat(
                db, seat=seat, enrolment=enrolment, course=course_obj
            )
            results.append(SeatDropResult(seat_id=seat_id, drop_successful=True))
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to drop seat {seat_id}: {ex}")
            results.append(
                SeatDropResult(seat_id=seat_id, drop_successful=False, error=str(ex))
            )

    return results


async def _drop_single_seat(
    db: AsyncSession, *, seat: Seat, enrolment: CourseEnrolment, course: Course
) -> None:
    project = await db.get(Project, enrolment.project_id)
    if project:
        await _clear_project_groups(project)

    # Remove the student from the vlab member group (if they claimed)
    if enrolment.claimed_by is not None:
        umr = UserMutationRepository()
        try:
            await umr.a_detach_user_from_group(
                user_id=enrolment.claimed_by,
                group_id=course.virtual_lab.member_group_id,
            )
        except Exception as ex:  # noqa: BLE001
            logger.warning(
                f"Failed to remove user {enrolment.claimed_by} from vlab member group: {ex}"
            )

    now = datetime.now(timezone.utc)
    is_early_drop = course.last_drop_date is not None and now < course.last_drop_date
    has_sufficient_balance = True

    if project:
        balance = await _get_project_balance(project.id)
        if balance is not None and balance < _MIN_RECOVERABLE_BALANCE:
            has_sufficient_balance = False

    can_recover = (
        is_early_drop and not seat.previously_dropped and has_sufficient_balance
    )

    if project:
        success = await accounting_cases.deplete_project_budget(
            virtual_lab_id=course.virtual_lab_id,
            project_id=project.id,
        )
        if not success:
            raise RuntimeError(
                f"Failed to deplete credits for project {project.id}, aborting drop"
            )

    enrolment.is_dropped = True

    if can_recover:
        seat.previously_dropped = True
        seat.enrolment_id = None
        seat.is_consumed = False
    else:
        seat.is_consumed = True

    await db.commit()
