"""Drop (release) seats for students in a course."""

from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.course import DropSeatsBody, SeatDropResult
from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, Project, Seat
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.usecases import accounting as accounting_cases


async def _remove_all_users_from_group(group_id: str) -> list[str]:
    """Remove every user from a Keycloak group. Returns list of user IDs that failed."""
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
    """Remove all users from the project member KC group (the student).

    Raises if any user could not be removed.
    """
    failed = await _remove_all_users_from_group(project.member_group_id)
    if failed:
        raise RuntimeError(
            f"Failed to remove {len(failed)} user(s) from project member group: {failed}"
        )


async def _reverse_project_budget(virtual_lab_id: UUID, project_id: UUID) -> None:
    """Reverse all unspent credits from project back to the vlab. Best-effort."""
    if settings.ACCOUNTING_BASE_URL is None:
        return

    try:
        # Get the project's current balance
        balance_resp = await accounting_cases.get_project_balance(project_id)
        balance = float(balance_resp.data.balance)

        if balance <= 0:
            return

        # Try reversing the full reported balance first. If it fails due to
        # rounding (reported > real), retry with 0.01 less.
        try:
            await accounting_cases.reverse_project_budget(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                amount=balance,
            )
            logger.info(
                f"Reversed {balance} credits from project {project_id} to vlab {virtual_lab_id}"
            )
            return
        except Exception:  # noqa: BLE001
            pass

        # Retry with reduced amount
        reverse_amount = round(balance - 0.01, 2)
        if reverse_amount <= 0:
            return

        await accounting_cases.reverse_project_budget(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=reverse_amount,
        )
        logger.info(
            f"Reversed {reverse_amount} credits (reduced) from project {project_id} to vlab {virtual_lab_id}"
        )
    except Exception as ex:  # noqa: BLE001
        logger.error(f"Failed to reverse budget for project {project_id}: {ex}")


async def drop_seats(
    db: AsyncSession,
    *,
    course: Course,
    payload: DropSeatsBody,
) -> list[SeatDropResult]:
    """Drop seats by ID: mark enrolment as dropped, handle KC/budget if activated.

    Validates all seats upfront — fails fast if any seat is invalid.
    Only KC/infra failures during the actual drop are treated as partial results.
    """
    # Validate all seats and load enrolments upfront
    seats_with_enrolments: list[tuple[Seat, CourseEnrolment]] = []
    results: list[SeatDropResult] = []

    for seat_id in payload.seat_ids:
        seat = await db.scalar(
            select(Seat).where(Seat.id == seat_id, Seat.course_id == course.id)
        )
        if seat is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Seat not found in this course",
                )
            )
            continue
        if seat.enrolment_id is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Seat has no enrolment (not assigned)",
                )
            )
            continue
        enrolment = await db.get(CourseEnrolment, seat.enrolment_id)
        if enrolment is None:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Enrolment not found for seat",
                )
            )
            continue
        if enrolment.is_dropped:
            results.append(
                SeatDropResult(
                    seat_id=seat_id,
                    drop_successful=False,
                    error="Enrolment is already dropped",
                )
            )
            continue
        seats_with_enrolments.append((seat, enrolment))

    # Proceed with drops
    for seat, enrolment in seats_with_enrolments:
        seat_id = seat.id
        try:
            await _drop_single_seat(db, seat=seat, enrolment=enrolment, course=course)
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
    """Execute the drop for a single seat.

    Clears KC groups and reverses budget for the linked project, then marks
    the enrolment as dropped and releases or consumes the seat.
    """
    project = await db.get(Project, enrolment.project_id)
    if project:
        await _clear_project_groups(project)
        await _reverse_project_budget(
            virtual_lab_id=course.virtual_lab_id, project_id=project.id
        )

    # Mark enrolment as dropped
    enrolment.is_dropped = True

    # Release or consume the seat based on drop date
    now = datetime.now(timezone.utc)
    if course.last_drop_date and now < course.last_drop_date:
        seat.enrolment_id = None
        seat.is_consumed = False
    else:
        seat.is_consumed = True

    await db.commit()
