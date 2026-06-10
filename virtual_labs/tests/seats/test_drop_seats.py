"""Tests for the drop-seats endpoint (POST /courses/{course_id}/drop_seats)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers


def _drop_payload(seat_ids: list[str] | None = None) -> dict:
    if seat_ids is None:
        seat_ids = [str(uuid4())]
    return {"seat_ids": seat_ids}


# ──────────────────────────────────────────────────────────────────────
# Authorization tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A user who is not a vlab admin cannot drop seats."""
    headers = get_headers("test-1")  # different user, not admin of this lab
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_drop_seats_fails_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """Returns 403 for a nonexistent course (verify_course_admin fails)."""
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{uuid4()}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_drop_seats_fails_without_auth(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Validation tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_rejects_empty_seat_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Empty seat_ids list is rejected by validation."""
    headers = get_headers()
    body = {"seat_ids": []}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_drop_seats_rejects_duplicate_seat_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Duplicate seat_id in request is rejected by validation."""
    headers = get_headers()
    seat_id = str(uuid4())
    body = {"seat_ids": [seat_id, seat_id]}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Non-existent seat test
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_fails_for_nonexistent_seat(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a seat that doesn't exist in the course returns 404."""
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Provision seats, assign one, then drop it successfully."""
    from unittest.mock import AsyncMock

    from virtual_labs.tests.seats.helpers import provision_seats
    from virtual_labs.tests.seats.test_assign_seats import mock_claim_email

    headers = get_headers()
    course_id = course_for_seats

    # Provision 2 seats
    await provision_seats(async_test_client, course_id, 2)

    # Assign one seat
    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_claim_email():
        assign_resp = await async_test_client.post(
            f"/courses/{course_id}/assign_seats",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]
    assert seat_id is not None

    # Drop the seat (mock accounting for the reverse)
    from unittest.mock import patch

    with (
        patch(
            "virtual_labs.usecases.course.drop_seats.accounting_cases.get_project_balance"
        ) as mock_balance,
        patch(
            "virtual_labs.usecases.course.drop_seats.accounting_cases.reverse_project_budget"
        ) as mock_reverse,
    ):
        mock_balance.return_value = AsyncMock(data=AsyncMock(balance="100.00"))
        mock_reverse.return_value = AsyncMock()

        drop_resp = await async_test_client.post(
            f"/courses/{course_id}/drop_seats",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] == seat_id
    assert results[0]["drop_successful"] is True
    assert results[0]["error"] is None
