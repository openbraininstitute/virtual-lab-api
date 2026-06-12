"""Tests for the expire_courses cron use case."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, CourseStatus
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_drop_seats import mock_assign_deps, mock_drop_deps
from virtual_labs.tests.utils import get_headers, session_context_factory
from virtual_labs.usecases.course.expire_courses import expire_courses

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _assign_seat(client: AsyncClient, course_id: str) -> str:
    """Provision and assign a seat. Returns the enrolment_id."""
    await provision_seats(client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    headers = get_headers()

    with mock_assign_deps():
        resp = await client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert resp.status_code == 200
    return resp.json()["results"][0]["enrolment_id"]


async def _expire_course(course_id: str) -> None:
    """Set course end_date to the past so it appears expired."""
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(end_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expire_courses_drops_enrolments(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Expired course enrolments are dropped by the cron."""
    course_id = course_for_seats
    enrolment_id = await _assign_seat(async_test_client, course_id)

    await _expire_course(course_id)

    with mock_drop_deps():
        async with session_context_factory() as session:
            summary = await expire_courses(session)

    assert summary["expired_courses_found"] >= 1
    assert summary["enrolments_dropped"] >= 1
    assert summary["enrolments_failed"] == 0

    async with session_context_factory() as session:
        enrolment = await session.get(CourseEnrolment, UUID(enrolment_id))
        assert enrolment is not None
        assert enrolment.is_dropped is True


@pytest.mark.asyncio
async def test_expire_courses_no_op_when_no_expired(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """No drops when no courses have ended."""
    await _assign_seat(async_test_client, course_for_seats)

    async with session_context_factory() as session:
        summary = await expire_courses(session)

    assert summary["expired_courses_found"] == 0
    assert summary["enrolments_dropped"] == 0


@pytest.mark.asyncio
async def test_expire_courses_idempotent(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Running the cron twice doesn't re-drop already-dropped enrolments."""
    course_id = course_for_seats
    await _assign_seat(async_test_client, course_id)
    await _expire_course(course_id)

    with mock_drop_deps():
        async with session_context_factory() as session:
            summary1 = await expire_courses(session)

        async with session_context_factory() as session:
            summary2 = await expire_courses(session)

    assert summary1["enrolments_dropped"] >= 1
    assert summary2["enrolments_dropped"] == 0


@pytest.mark.asyncio
async def test_expire_courses_processes_voided_too(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Voided courses past end_date still get their enrolments dropped."""
    course_id = course_for_seats
    enrolment_id = await _assign_seat(async_test_client, course_id)

    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(
                end_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
                status=CourseStatus.VOIDED,
            )
        )
        await session.commit()

    with mock_drop_deps():
        async with session_context_factory() as session:
            summary = await expire_courses(session)

    assert summary["enrolments_dropped"] >= 1

    async with session_context_factory() as session:
        enrolment = await session.get(CourseEnrolment, UUID(enrolment_id))
        assert enrolment is not None
        assert enrolment.is_dropped is True


@pytest.mark.asyncio
async def test_expire_courses_handles_kc_failure_gracefully(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If KC cleanup fails for one enrolment, it stays undropped for retry."""
    course_id = course_for_seats
    enrolment_id = await _assign_seat(async_test_client, course_id)
    await _expire_course(course_id)

    with patch(
        "virtual_labs.usecases.course.drop_seats._clear_project_groups",
        new_callable=AsyncMock,
        side_effect=RuntimeError("KC unavailable"),
    ):
        async with session_context_factory() as session:
            summary = await expire_courses(session)

    assert summary["enrolments_failed"] >= 1

    async with session_context_factory() as session:
        enrolment = await session.get(CourseEnrolment, UUID(enrolment_id))
        assert enrolment is not None
        assert enrolment.is_dropped is False


@pytest.mark.asyncio
async def test_expire_courses_multiple_enrolments(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Multiple enrolments in one expired course are all dropped."""
    course_id = course_for_seats

    enrolment_ids = []
    for _ in range(3):
        eid = await _assign_seat(async_test_client, course_id)
        enrolment_ids.append(eid)

    await _expire_course(course_id)

    with mock_drop_deps():
        async with session_context_factory() as session:
            summary = await expire_courses(session)

    assert summary["enrolments_dropped"] == 3

    async with session_context_factory() as session:
        for eid in enrolment_ids:
            enrolment = await session.get(CourseEnrolment, UUID(eid))
            assert enrolment is not None
            assert enrolment.is_dropped is True
