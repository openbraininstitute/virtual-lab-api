"""Tests for POST /courses/activate-enrolments."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, CourseStatus
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_assign_seats import mock_assign_accounting
from virtual_labs.tests.utils import get_headers, session_context_factory

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _assign_and_claim(
    client: AsyncClient,
    course_id: str,
    *,
    claim_user: str = "test",
    set_start_in_past: bool = True,
) -> str:
    """Provision a seat, assign it, claim it, and return the enrolment_id."""
    await provision_seats(client, course_id, 1)

    # By default, set start_date to the past so activation passes the "not started" check
    if set_start_in_past:
        async with session_context_factory() as session:
            await session.execute(
                update(Course)
                .where(Course.id == UUID(course_id))
                .values(start_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
            )
            await session.commit()

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    headers = get_headers()

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=1000.0))
        mocks.transfer.return_value = AsyncMock()
        assign_resp = await client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    enrolment_id = assign_resp.json()["results"][0]["enrolment_id"]

    # Claim the enrolment
    claim_resp = await client.post(
        f"/courses/{course_id}/claim",
        json={"enrolment_id": enrolment_id},
        headers=get_headers(claim_user),
    )
    assert claim_resp.status_code == 200

    return enrolment_id


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolments_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Activating a claimed enrolment adds user to KC groups and sets activated_at."""
    course_id = course_for_seats
    enrolment_id = await _assign_and_claim(async_test_client, course_id)

    with patch(
        "virtual_labs.usecases.course.activate_enrolments._add_to_groups",
        new_callable=AsyncMock,
    ) as mock_groups:
        response = await async_test_client.post(
            "/courses/activate-enrolments",
            headers=get_headers(),
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["enrolment_id"] == enrolment_id
    assert results[0]["activated"] is True
    assert results[0]["project_id"] is not None
    assert results[0]["error"] is None
    mock_groups.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_enrolments_idempotent(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Calling activate twice — second call returns empty results."""
    course_id = course_for_seats
    await _assign_and_claim(async_test_client, course_id)

    with patch(
        "virtual_labs.usecases.course.activate_enrolments._add_to_groups",
        new_callable=AsyncMock,
    ):
        # First activation
        resp1 = await async_test_client.post(
            "/courses/activate-enrolments",
            headers=get_headers(),
        )
    assert resp1.status_code == 200
    assert len(resp1.json()["results"]) == 1

    # Second activation — nothing to activate
    with patch(
        "virtual_labs.usecases.course.activate_enrolments._add_to_groups",
        new_callable=AsyncMock,
    ) as mock_groups:
        resp2 = await async_test_client.post(
            "/courses/activate-enrolments",
            headers=get_headers(),
        )
    assert resp2.status_code == 200
    assert len(resp2.json()["results"]) == 0
    mock_groups.assert_not_awaited()


@pytest.mark.asyncio
async def test_activate_enrolments_no_pending(
    async_test_client: AsyncClient,
) -> None:
    """When user has no pending enrolments, returns empty results."""
    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers=get_headers(),
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


# ──────────────────────────────────────────────────────────────────────
# Restriction tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolments_skips_ended_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Enrolments in courses past end_date are skipped."""
    course_id = course_for_seats
    enrolment_id = await _assign_and_claim(async_test_client, course_id)

    # Set end_date to the past
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(end_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers=get_headers(),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["enrolment_id"] == enrolment_id
    assert results[0]["activated"] is False
    assert "ended" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_activate_enrolments_skips_not_started_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Enrolments in courses before start_date are skipped."""
    course_id = course_for_seats
    enrolment_id = await _assign_and_claim(
        async_test_client, course_id, set_start_in_past=False
    )

    # Set start_date to the future
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(start_date=datetime(2099, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers=get_headers(),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["enrolment_id"] == enrolment_id
    assert results[0]["activated"] is False
    assert "not started" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_activate_enrolments_skips_voided_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Enrolments in voided courses are skipped."""
    course_id = course_for_seats
    await _assign_and_claim(async_test_client, course_id)

    # Void the course
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(status=CourseStatus.VOIDED)
        )
        await session.commit()

    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers=get_headers(),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["activated"] is False
    assert "voided" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_activate_enrolments_skips_dropped(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropped enrolments are not picked up for activation."""
    course_id = course_for_seats
    enrolment_id = await _assign_and_claim(async_test_client, course_id)

    # Mark as dropped
    async with session_context_factory() as session:
        await session.execute(
            update(CourseEnrolment)
            .where(CourseEnrolment.id == UUID(enrolment_id))
            .values(is_dropped=True)
        )
        await session.commit()

    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers=get_headers(),
    )

    assert response.status_code == 200
    # Dropped enrolments are filtered out by the query — not even in results
    assert response.json()["results"] == []


@pytest.mark.asyncio
async def test_activate_enrolments_kc_failure_graceful(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If KC group add fails, activation reports error but doesn't crash."""
    course_id = course_for_seats
    enrolment_id = await _assign_and_claim(async_test_client, course_id)

    with patch(
        "virtual_labs.usecases.course.activate_enrolments._add_to_groups",
        new_callable=AsyncMock,
        side_effect=Exception("KC unavailable"),
    ):
        response = await async_test_client.post(
            "/courses/activate-enrolments",
            headers=get_headers(),
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["enrolment_id"] == enrolment_id
    assert results[0]["activated"] is False
    assert "try again" in results[0]["error"].lower()


# ──────────────────────────────────────────────────────────────────────
# Auth tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_enrolments_unauthenticated(
    async_test_client: AsyncClient,
) -> None:
    """Request without auth is rejected."""
    response = await async_test_client.post(
        "/courses/activate-enrolments",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401
