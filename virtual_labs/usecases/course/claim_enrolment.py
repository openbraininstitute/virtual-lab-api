"""Claim an enrolment — student validates their link and we record who claimed it."""

import asyncio
from datetime import datetime, timezone
from http import HTTPStatus
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.ledger import LedgerAction, ledger_container
from virtual_labs.infrastructure.db.models import (
    CourseEnrolment,
    CourseStatus,
    Project,
    VirtualLab,
)
from virtual_labs.infrastructure.kc.config import KeycloakRealm


def _make_remove_from_group(user_id: UUID, group_id: str) -> LedgerAction:
    async def _undo() -> None:
        await KeycloakRealm.a_group_user_remove(user_id=user_id, group_id=group_id)

    return _undo


async def claim_enrolment(
    db: AsyncSession,
    *,
    enrolment_id: UUID,
    user_id: UUID,
) -> CourseEnrolment:
    """Validate the claim link and set `claimed_by` on the enrolment.

    Checks:
    1. Enrolment exists.
    2. Enrolment is not dropped.
    3. Enrolment is not already claimed.
    4. Course is active.

    Returns the updated enrolment.
    """
    result = await db.execute(
        select(CourseEnrolment)
        .where(CourseEnrolment.id == enrolment_id)
        .with_for_update(of=CourseEnrolment)
    )
    enrolment = result.scalar_one_or_none()

    if enrolment is None:
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="Enrolment not found",
        )

    if enrolment.is_dropped:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="This enrolment has been dropped",
        )

    if enrolment.claimed_by is not None:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="This enrolment has already been claimed",
        )

    # Verify the course is still active
    course = enrolment.course
    if course.status != CourseStatus.ACTIVE:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message=f"Cannot claim enrolment: course is in '{course.status.value}' status",
        )

    now = datetime.now(timezone.utc)
    if course.end_date is not None and now >= course.end_date:
        raise VliError(
            error_code=VliErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            message="Cannot claim enrolment: course has ended",
        )

    # Read course data before commit — after refresh the relationship is expired
    course = enrolment.course
    virtual_lab_id = course.virtual_lab_id
    course_started = course.start_date is None or now >= course.start_date.replace(
        tzinfo=timezone.utc
    )
    project_id = enrolment.project_id

    project = await db.get(Project, project_id)
    assert project is not None
    virtual_lab = await db.get(VirtualLab, virtual_lab_id)
    assert virtual_lab is not None
    target_group_id = (
        project.member_group_id if course_started else project.waitlisted_group_id
    )

    try:
        async with ledger_container() as comp:
            if target_group_id is not None:
                await asyncio.gather(
                    KeycloakRealm.a_group_user_add(
                        user_id=user_id, group_id=target_group_id
                    ),
                    KeycloakRealm.a_group_user_add(
                        user_id=user_id, group_id=str(virtual_lab.member_group_id)
                    ),
                )
                comp.push(_make_remove_from_group(user_id, target_group_id))
                comp.push(
                    _make_remove_from_group(user_id, str(virtual_lab.member_group_id))
                )

            enrolment.claimed_by = user_id
            await db.commit()
            await db.refresh(enrolment)
    except VliError:
        raise
    except Exception as exc:
        raise VliError(
            error_code=VliErrorCode.EXTERNAL_SERVICE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Failed to claim enrolment",
        ) from exc

    logger.info(
        f"Enrolment {enrolment_id} claimed by user {user_id} (course={enrolment.course_id})"
    )

    return enrolment
