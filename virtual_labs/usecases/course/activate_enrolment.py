"""Activate a single claimed enrolment — add to member group, remove from waitlisted."""

import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import Ledger, LedgerAction, ledger_container
from virtual_labs.infrastructure.db.models import CourseEnrolment, CourseStatus
from virtual_labs.infrastructure.kc.config import KeycloakRealm


def _make_remove_from_group(user_id: UUID, group_id: str) -> LedgerAction:
    async def _undo() -> None:
        await KeycloakRealm.a_group_user_remove(user_id=user_id, group_id=group_id)

    return _undo


async def _activate_in_kc(
    *,
    user_id: UUID,
    project_member_group_id: str,
    vlab_member_group_id: str,
    waitlisted_group_id: str | None,
    comp: Ledger,
) -> None:
    """Add user to member groups (with compensation) then remove from waitlisted."""
    await asyncio.gather(
        KeycloakRealm.a_group_user_add(
            user_id=user_id, group_id=project_member_group_id
        ),
        KeycloakRealm.a_group_user_add(user_id=user_id, group_id=vlab_member_group_id),
    )
    comp.push(_make_remove_from_group(user_id, project_member_group_id))
    comp.push(_make_remove_from_group(user_id, vlab_member_group_id))

    if waitlisted_group_id is not None:
        await KeycloakRealm.a_group_user_remove(
            user_id=user_id, group_id=waitlisted_group_id
        )


async def activate_enrolment(
    db: AsyncSession,
    *,
    course_id: UUID,
    user_id: UUID,
) -> CourseEnrolment:
    """Activate the calling user's enrolment in the given course.

    Idempotent: if already activated, returns the enrolment as-is.
    Fails with 404 if the user has no enrolment in the course, 409 if the
    enrolment is dropped or the course is not in a valid state.
    Uses the ledger to compensate KC group adds on failure.
    """
    result = await db.execute(
        select(CourseEnrolment)
        .join(CourseEnrolment.project)
        .options(contains_eager(CourseEnrolment.project))
        .where(
            CourseEnrolment.course_id == course_id,
            CourseEnrolment.claimed_by == user_id,
        )
        .with_for_update(of=CourseEnrolment)
    )
    enrolment = result.scalars().unique().one_or_none()

    if enrolment is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="No enrolment found for this user in the course",
        )

    if enrolment.is_dropped:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Cannot activate a dropped enrolment",
        )

    # Idempotency: already activated → return success
    if enrolment.activated_at is not None:
        return enrolment

    course = enrolment.course
    now = datetime.now(timezone.utc)

    if course.status != CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Course is in '{course.status.value}' status",
        )

    if course.end_date is not None and now >= course.end_date.replace(
        tzinfo=timezone.utc
    ):
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Course has ended",
        )

    if course.start_date is not None and now < course.start_date.replace(
        tzinfo=timezone.utc
    ):
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Course has not started yet",
        )

    project = enrolment.project
    vlab = course.virtual_lab

    async with ledger_container() as comp:
        await _activate_in_kc(
            user_id=user_id,
            project_member_group_id=project.member_group_id,
            vlab_member_group_id=vlab.member_group_id,
            waitlisted_group_id=project.waitlisted_group_id,
            comp=comp,
        )

        enrolment.activated_at = now
        await db.commit()

    return enrolment
