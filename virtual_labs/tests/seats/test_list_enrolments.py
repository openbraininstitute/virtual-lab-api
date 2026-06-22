"""Tests for GET /courses/{course_id}/enrolments (list enrolments for a course)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_assign_seats import mock_assign_accounting
from virtual_labs.tests.utils import get_headers

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _assign_students(
    client: AsyncClient, course_id: str, count: int = 1
) -> list[dict]:
    """Provision and assign seats. Returns the assignment results."""
    await provision_seats(client, course_id, count)

    students = [
        {
            "student_id": f"stu-{uuid4().hex[:8]}",
            "email": f"{uuid4().hex[:8]}@uni.org",
        }
        for _ in range(count)
    ]
    headers = get_headers()

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=5000.0))
        mocks.transfer.return_value = AsyncMock()
        resp = await client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": students},
            headers=headers,
        )
    assert resp.status_code == 200
    return resp.json()["results"]


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_enrolments_returns_all(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns all enrolments for the course."""
    course_id = course_for_seats
    results = await _assign_students(async_test_client, course_id, 3)

    headers = get_headers()
    response = await async_test_client.get(
        f"/courses/{course_id}/enrolments",
        headers=headers,
    )

    assert response.status_code == 200
    enrolments = response.json()["enrolments"]
    assert len(enrolments) == 3

    # All enrolment IDs from assignment should be present
    assigned_ids = {r["enrolment_id"] for r in results}
    returned_ids = {e["id"] for e in enrolments}
    assert assigned_ids == returned_ids


@pytest.mark.asyncio
async def test_list_enrolments_empty(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Returns empty list when no enrolments exist."""
    headers = get_headers()
    response = await async_test_client.get(
        f"/courses/{course_for_seats}/enrolments",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["enrolments"] == []


@pytest.mark.asyncio
async def test_list_enrolments_contains_expected_fields(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Each enrolment has the expected fields including nested seat."""
    course_id = course_for_seats
    await _assign_students(async_test_client, course_id, 1)

    headers = get_headers()
    response = await async_test_client.get(
        f"/courses/{course_id}/enrolments",
        headers=headers,
    )

    assert response.status_code == 200
    enrolment = response.json()["enrolments"][0]

    # Enrolment fields
    assert "id" in enrolment
    assert "course_id" in enrolment
    assert "project_id" in enrolment
    assert "contact_email" in enrolment
    assert "student_id" in enrolment
    assert "claimed_by" in enrolment
    assert "activated_at" in enrolment
    assert "is_dropped" in enrolment
    assert "created_at" in enrolment

    # Nested seat
    assert "seat" in enrolment
    seat = enrolment["seat"]
    assert seat is not None
    assert "id" in seat
    assert "course_id" in seat
    assert "batch_id" in seat
    assert "is_consumed" in seat
    assert "credit_value" in seat
    assert "expiry_date" in seat


@pytest.mark.asyncio
async def test_list_enrolments_includes_claimed_status(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """After claiming, the enrolment shows claimed_by."""
    course_id = course_for_seats
    results = await _assign_students(async_test_client, course_id, 1)
    enrolment_id = results[0]["enrolment_id"]

    # Claim it
    headers = get_headers()
    claim_resp = await async_test_client.post(
        f"/courses/{course_id}/claim",
        json={"enrolment_id": enrolment_id},
        headers=headers,
    )
    assert claim_resp.status_code == 200

    # List and verify
    response = await async_test_client.get(
        f"/courses/{course_id}/enrolments",
        headers=headers,
    )

    assert response.status_code == 200
    enrolment = response.json()["enrolments"][0]
    assert enrolment["claimed_by"] is not None
    assert enrolment["is_dropped"] is False


# ──────────────────────────────────────────────────────────────────────
# Auth tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_enrolments_forbidden_for_non_admin(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Non-admin user gets 403."""
    headers = get_headers("test-1")
    response = await async_test_client.get(
        f"/courses/{course_for_seats}/enrolments",
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_enrolments_forbidden_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """Nonexistent course returns 403."""
    headers = get_headers()
    response = await async_test_client.get(
        f"/courses/{uuid4()}/enrolments",
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_enrolments_unauthenticated(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """No auth returns 401."""
    response = await async_test_client.get(
        f"/courses/{course_for_seats}/enrolments",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401
