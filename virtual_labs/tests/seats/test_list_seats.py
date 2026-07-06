"""Tests for GET /seats/courses/{course_id} (list seats for a course).

This endpoint uses parse_auth_grants (vlab admin check via KC groups),
NOT verify_service_admin. The test user "test" is the lab owner/admin.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_drop_seats import mock_assign_deps
from virtual_labs.tests.utils import get_headers

# ──────────────────────────────────────────────────────────────────────
# Happy path
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_seats_returns_provisioned_seats(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Vlab admin can list seats for a course they own."""
    await provision_seats(async_test_client, course_for_seats, number_of_seats=3)

    headers = get_headers()  # "test" user is the lab owner/admin
    response = await async_test_client.get(
        f"/seats/courses/{course_for_seats}", headers=headers
    )

    assert response.status_code == 200
    result = response.json()
    assert "data" in result
    assert len(result["data"]) == 3
    assert "pagination" in result


@pytest.mark.asyncio
async def test_list_seats_returns_empty_list_when_no_seats(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Vlab admin gets an empty list when no seats have been provisioned."""
    headers = get_headers()
    response = await async_test_client.get(
        f"/seats/courses/{course_for_seats}", headers=headers
    )

    assert response.status_code == 200
    result = response.json()
    assert result["data"] == []


@pytest.mark.asyncio
async def test_list_seats_contains_expected_fields(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Each seat in the response has all the required fields."""
    await provision_seats(async_test_client, course_for_seats, number_of_seats=1)

    headers = get_headers()
    response = await async_test_client.get(
        f"/seats/courses/{course_for_seats}", headers=headers
    )

    assert response.status_code == 200
    seat = response.json()["data"][0]
    assert "id" in seat
    assert "course_id" in seat
    assert "institution_id" in seat
    assert "batch_id" in seat
    assert "is_consumed" in seat
    assert "expiry_date" in seat
    assert "created_at" in seat
    assert seat["course_id"] == course_for_seats
    assert seat["is_consumed"] is False


# ──────────────────────────────────────────────────────────────────────
# Authorization: non-admin user
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_seats_forbidden_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A user who is not a vlab admin gets 403 (no info leak about course existence)."""
    headers = get_headers("test-1")  # different user, not admin of this lab
    response = await async_test_client.get(
        f"/seats/courses/{course_for_seats}", headers=headers
    )

    assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Authorization: course does not exist
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_seats_forbidden_for_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """A request for a non-existent course returns 403 (not 404) to avoid leaking info."""
    headers = get_headers()
    response = await async_test_client.get(f"/seats/courses/{uuid4()}", headers=headers)

    assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Authorization: no auth token
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_seats_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    """Missing/empty auth token returns 401."""
    response = await async_test_client.get(
        f"/seats/courses/{uuid4()}",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Enrolment visibility
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_seats_shows_enrolment_for_assigned_seats(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Seats with an enrolment include it in the response; unassigned seats have enrolment=None."""
    from uuid import uuid4 as uuid

    # Provision 3 seats
    await provision_seats(async_test_client, course_for_seats, number_of_seats=3)

    headers = get_headers()

    # Assign 2 of the 3 seats
    students = [
        {"student_id": f"stu-{uuid().hex[:8]}", "email": f"{uuid().hex[:8]}@uni.org"},
        {"student_id": f"stu-{uuid().hex[:8]}", "email": f"{uuid().hex[:8]}@uni.org"},
    ]
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_for_seats}/assign",
            json={"students": students},
            headers=headers,
        )
    assert assign_resp.status_code == 200

    # List seats
    response = await async_test_client.get(
        f"/seats/courses/{course_for_seats}", headers=headers
    )
    assert response.status_code == 200
    seats = response.json()["data"]

    # 2 seats should have enrolments, 1 should not
    assigned = [s for s in seats if s["enrolment"] is not None]
    unassigned = [s for s in seats if s["enrolment"] is None]
    assert len(assigned) == 2
    assert len(unassigned) == 1
