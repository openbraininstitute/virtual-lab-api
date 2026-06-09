"""Drop (release) seats for students in a course."""

from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.course import DropSeatsBody, SeatDropResult
from virtual_labs.infrastructure.db.models import Course, Project, Seat
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository


async def _remove_all_users_from_group(group_id: str) -> None:
    """Remove every user from a Keycloak group."""
    gqr = GroupQueryRepository()
    umr = UserMutationRepository()

    users = await gqr.a_retrieve_group_users(group_id=group_id)
    for user in users:
        try:
            await umr.a_detach_user_from_group(user_id=UUID(user.id), group_id=group_id)
        except Exception as ex:  # noqa: BLE001
            logger.warning(
                f"Failed to remove user {user.id} from group {group_id}: {ex}"
            )


async def _clear_project_groups(project: Project) -> None:
    """Remove all users from both admin and member KC groups of a project."""
    await _remove_all_users_from_group(project.admin_group_id)
    await _remove_all_users_from_group(project.member_group_id)


async def drop_seats(
    db: AsyncSession,
    *,
    course: Course,
    payload: DropSeatsBody,
) -> list[SeatDropResult]:
    """Drop seats by ID: clear KC groups, soft-delete the project, release the seat.

    Validates all seats upfront — fails fast if any seat is invalid.
    Only KC/infra failures during the actual drop are treated as partial results.
    """
    # Validate all seats upfront
    seats_with_projects: list[tuple[Seat, Project]] = []
    for seat_id in payload.seat_ids:
        seat = await db.scalar(
            select(Seat).where(Seat.id == seat_id, Seat.course_id == course.id)
        )
        if seat is None:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
                message=f"Seat {seat_id} not found in this course",
            )
        if seat.active_project_id is None:
            raise VliError(
                error_code=VliErrorCode.INVALID_REQUEST,
                http_status_code=HTTPStatus.CONFLICT,
                message=f"Seat {seat_id} has no active project (not assigned)",
            )
        project = await db.get(Project, seat.active_project_id)
        if project is None:
            raise VliError(
                error_code=VliErrorCode.ENTITY_NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
                message=f"Project {seat.active_project_id} not found for seat {seat_id}",
            )
        seats_with_projects.append((seat, project))

    # All valid — proceed with drops
    results: list[SeatDropResult] = []
    for seat, project in seats_with_projects:
        try:
            await _drop_single_seat(db, seat=seat, project=project, course=course)
            results.append(SeatDropResult(seat_id=seat.id, drop_successful=True))
        except Exception as ex:  # noqa: BLE001
            logger.error(f"Failed to drop seat {seat.id}: {ex}")
            results.append(
                SeatDropResult(seat_id=seat.id, drop_successful=False, error=str(ex))
            )

    return results


async def _drop_single_seat(
    db: AsyncSession, *, seat: Seat, project: Project, course: Course
) -> None:
    """Execute the drop: clear KC groups, soft-delete project, release/consume seat."""
    # 1. Remove all users from the project's KC groups
    await _clear_project_groups(project)

    # 2. Soft-delete the project
    project.deleted = True
    project.contact_email = None

    # 3. Release or consume the seat based on drop date.
    #    Keep active_project_id as a historical artifact — assignment checks
    #    both is_consumed=False AND active_project_id IS NULL.
    now = datetime.now(timezone.utc)
    if course.last_drop_date and now < course.last_drop_date:
        # Before last_drop_date: release the seat so it can be re-assigned
        seat.active_project_id = None
        seat.is_consumed = False
    else:
        # After last_drop_date: seat is spent
        seat.is_consumed = True

    await db.commit()
