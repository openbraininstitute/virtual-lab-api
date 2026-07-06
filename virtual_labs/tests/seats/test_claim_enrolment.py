"""Tests for the claim-enrolment endpoint (POST /courses/claim)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import CourseEnrolment
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_assign_seats import mock_assign_accounting
from virtual_labs.tests.utils import get_headers, session_context_factory

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _create_enrolment(
    client: AsyncClient, course_id: str, *, student_id: str | None = None
) -> str:
    """Assign a single seat and return the enrolment_id."""
    await provision_seats(client, course_id, 1)

    student = {
        "student_id": student_id or f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = {"students": [student]}
    headers = get_headers()

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=1000.0))
        mocks.transfer.return_value = AsyncMock()
        response = await client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    return results[0]["enrolment_id"]


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_enrolment_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A valid claim sets claimed_by and returns enrolment details."""
    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == enrolment_id
    assert data["course_id"] == course_id
    assert data["claimed_by"] is not None
    assert data["project_id"] is not None
    assert data["contact_email"] is not None
    assert data["student_id"] is not None
    # Course summary
    assert data["course"]["id"] == course_id
    assert data["course"]["virtual_lab_name"] is not None
    assert data["course"]["institution_name"] is not None


@pytest.mark.asyncio
async def test_claim_enrolment_by_different_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A different authenticated user can claim (the link is what matters, not a specific user)."""
    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    headers = get_headers("test-1")
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["claimed_by"] is not None


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_enrolment_not_found(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming a non-existent enrolment returns 404."""
    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": str(uuid4())},
        headers=headers,
    )

    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_already_claimed(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming an already-claimed enrolment returns 409."""
    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)
    headers = get_headers()

    # First claim succeeds
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )
    assert response.status_code == 200

    # Second claim fails
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 409
    assert "already been claimed" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_dropped(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming a dropped enrolment returns 409."""
    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    # Manually mark as dropped in the DB
    from uuid import UUID

    async with session_context_factory() as session:
        await session.execute(
            update(CourseEnrolment)
            .where(CourseEnrolment.id == UUID(enrolment_id))
            .values(is_dropped=True)
        )
        await session.commit()

    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 409
    assert "dropped" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_voided_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming on a voided course returns 409."""
    from uuid import UUID

    from virtual_labs.infrastructure.db.models import Course, CourseStatus

    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    # Void the course directly in the DB
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(status=CourseStatus.VOIDED)
        )
        await session.commit()

    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 409
    assert "voided" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_draft_course(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming on a draft course returns 409."""
    from uuid import UUID

    from virtual_labs.infrastructure.db.models import Course, CourseStatus

    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    # Revert the course to draft in the DB
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(status=CourseStatus.DRAFT)
        )
        await session.commit()

    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 409
    assert "draft" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_course_ended(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claiming after the course end_date returns 409."""
    from datetime import datetime, timezone
    from uuid import UUID

    from virtual_labs.infrastructure.db.models import Course

    course_id = course_for_seats
    enrolment_id = await _create_enrolment(async_test_client, course_id)

    # Set end_date to the past
    async with session_context_factory() as session:
        await session.execute(
            update(Course)
            .where(Course.id == UUID(course_id))
            .values(end_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )

    assert response.status_code == 409
    assert "ended" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_claim_enrolment_invalid_enrolment_id_format(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A malformed enrolment_id returns 422 (validation error)."""
    headers = get_headers()
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": "not-a-uuid"},
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_claim_enrolment_unauthenticated(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A request without a valid Authorization header is rejected."""
    response = await async_test_client.post(
        "/courses/claim",
        json={"enrolment_id": str(uuid4())},
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401
