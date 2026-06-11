"""Activate claimed enrolments — add student to KC project/vlab member groups."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from virtual_labs.infrastructure.db.models import (
    CourseEnrolment,
    CourseStatus,
)
from virtual_labs.infrastructure.kc.config import KeycloakRealm


async def _add_to_groups(
    user_id: UUID,
    project_member_group_id: str,
    vlab_member_group_id: str,
) -> None:
    """Add the user to project member and vlab member KC groups."""
    await asyncio.gather(
        KeycloakRealm.a_group_user_add(
            user_id=user_id,
            group_id=project_member_group_id,
        ),
        KeycloakRealm.a_group_user_add(
            user_id=user_id,
            group_id=vlab_member_group_id,
        ),
    )


async def activate_enrolments(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[dict]:
    """Activate all claimed-but-not-yet-activated enrolments for a user.

    For each qualifying enrolment:
    1. Validate: course active, not past end_date, not dropped.
    2. Add user to project member group + vlab member group in KC.
    3. Set activated_at timestamp.

    Returns a list of results (one per enrolment attempted).
    """
    now = datetime.now(timezone.utc)

    # Find all enrolments claimed by this user that haven't been activated yet
    result = await db.execute(
        select(CourseEnrolment)
        .options(joinedload(CourseEnrolment.project))
        .where(
            CourseEnrolment.claimed_by == user_id,
            CourseEnrolment.activated_at.is_(None),
            CourseEnrolment.is_dropped.is_(False),
        )
        .with_for_update(of=CourseEnrolment)
    )
    enrolments = result.scalars().unique().all()

    if not enrolments:
        return []

    results: list[dict] = []

    for enrolment in enrolments:
        course = enrolment.course
        enrolment_id = enrolment.id

        # Skip if course is not active
        if course.status != CourseStatus.ACTIVE:
            results.append(
                {
                    "enrolment_id": enrolment_id,
                    "activated": False,
                    "error": f"Course is in '{course.status.value}' status",
                }
            )
            continue

        # Skip if course has ended
        if course.end_date is not None and now >= course.end_date:
            results.append(
                {
                    "enrolment_id": enrolment_id,
                    "activated": False,
                    "error": "Course has ended",
                }
            )
            continue

        # Skip if course hasn't started yet
        if course.start_date is not None and now < course.start_date:
            results.append(
                {
                    "enrolment_id": enrolment_id,
                    "activated": False,
                    "error": "Course has not started yet",
                }
            )
            continue

        # Project is loaded via joinedload in the query
        project = enrolment.project

        # Vlab is loaded via Course.virtual_lab (lazy="joined")
        vlab = course.virtual_lab

        # Add user to KC groups
        try:
            await _add_to_groups(
                user_id=user_id,
                project_member_group_id=project.member_group_id,
                vlab_member_group_id=vlab.member_group_id,
            )
        except Exception as ex:  # noqa: BLE001
            logger.error(
                f"Failed to add user {user_id} to KC groups for "
                f"enrolment {enrolment_id}: {ex}"
            )
            results.append(
                {
                    "enrolment_id": enrolment_id,
                    "activated": False,
                    "error": "Failed to grant access — please try again later",
                }
            )
            continue

        # Mark as activated
        enrolment.activated_at = now
        results.append(
            {
                "enrolment_id": enrolment_id,
                "activated": True,
                "project_id": project.id,
                "error": None,
            }
        )

    await db.commit()

    activated_count = sum(1 for r in results if r["activated"])
    logger.info(
        f"Activated {activated_count}/{len(results)} enrolments for user {user_id}"
    )

    return results
