"""Tests for the drop-seats endpoint (POST /seats/courses/{course_id}/drop)."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.utils import get_headers


def _drop_payload(seat_ids: list[str] | None = None) -> dict:
    if seat_ids is None:
        seat_ids = [str(uuid4())]
    return {"seat_ids": seat_ids}


@contextmanager
def mock_assign_deps():
    """Mock fund_project + email for assignment calls inside drop tests."""
    with (
        patch(
            "virtual_labs.usecases.project.create_new_project.ensure_accounting_initialization",
            new_callable=AsyncMock,
        ),
        patch(
            "virtual_labs.usecases.course.assign_seats.accounting_cases.fund_project",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "virtual_labs.usecases.course.assign_seats.send_enrolment_claim_email",
            new_callable=AsyncMock,
        ),
    ):
        yield


@contextmanager
def mock_drop_deps():
    """Mock accounting deps for the drop flow."""
    with (
        patch(
            "virtual_labs.usecases.course.drop_seats._clear_project_groups",
            new_callable=AsyncMock,
        ),
        patch(
            "virtual_labs.usecases.course.drop_seats.accounting_cases.deplete_project_budget",
            new_callable=AsyncMock,
            return_value=200.0,
        ),
    ):
        yield


# ──────────────────────────────────────────────────────────────────────
# Authorization tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    headers = get_headers("test-1")
    body = _drop_payload()

    response = await async_test_client.post(
        f"/seats/courses/{course_for_seats}/drop",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_drop_seats_fails_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/seats/courses/{uuid4()}/drop",
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
        f"/seats/courses/{course_for_seats}/drop",
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
    headers = get_headers()
    body = {"seat_ids": []}

    response = await async_test_client.post(
        f"/seats/courses/{course_for_seats}/drop",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_drop_seats_rejects_duplicate_seat_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    headers = get_headers()
    seat_id = str(uuid4())
    body = {"seat_ids": [seat_id, seat_id]}

    response = await async_test_client.post(
        f"/seats/courses/{course_for_seats}/drop",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Non-existent seat test
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_nonexistent_seat_returns_error_in_results(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    headers = get_headers()
    body = _drop_payload()

    response = await async_test_client.post(
        f"/seats/courses/{course_for_seats}/drop",
        json=body,
        headers=headers,
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "not found" in results[0]["error"].lower()


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Provision seats, assign one, then drop it successfully."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    with mock_drop_deps():
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] == seat_id
    assert results[0]["drop_successful"] is True
    assert results[0]["error"] is None


@pytest.mark.asyncio
async def test_drop_seats_post_activation(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Drop a seat after activation: KC groups cleared and budget depleted."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    with (
        patch(
            "virtual_labs.usecases.course.drop_seats._clear_project_groups",
            new_callable=AsyncMock,
        ) as mock_clear_groups,
        patch(
            "virtual_labs.usecases.course.drop_seats.accounting_cases.deplete_project_budget",
            new_callable=AsyncMock,
            return_value=200.0,
        ) as mock_deplete,
    ):
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is True

    mock_clear_groups.assert_awaited_once()
    mock_deplete.assert_awaited_once()


@pytest.mark.asyncio
async def test_drop_seats_post_activation_kc_failure(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Drop fails gracefully when KC group cleanup fails."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Mock KC to fail
    with (
        patch(
            "virtual_labs.usecases.course.drop_seats._clear_project_groups",
            new_callable=AsyncMock,
            side_effect=RuntimeError("KC unavailable"),
        ),
    ):
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert results[0]["error"] is not None


# ──────────────────────────────────────────────────────────────────────
# Multi-seat and edge-case tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_unassigned_seat(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a provisioned but unassigned seat returns 'no enrolment'."""
    headers = get_headers()
    course_id = course_for_seats

    prov = await provision_seats(async_test_client, course_id, 1)
    seat_id = prov["seats"][0]["id"]

    drop_resp = await async_test_client.post(
        f"/seats/courses/{course_id}/drop",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "no enrolment" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_drop_seats_already_dropped(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping a seat that was already dropped (early): seat is recycled, shows 'no enrolment'."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Drop it once (early drop — seat is recycled)
    with mock_drop_deps():
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )
    assert drop_resp.status_code == 200
    assert drop_resp.json()["results"][0]["drop_successful"] is True

    # Drop it again — seat now has no enrolment (recycled)
    drop_resp2 = await async_test_client.post(
        f"/seats/courses/{course_id}/drop",
        json={"seat_ids": [seat_id]},
        headers=headers,
    )
    assert drop_resp2.status_code == 200
    results = drop_resp2.json()["results"]
    assert len(results) == 1
    assert results[0]["drop_successful"] is False
    assert "no enrolment" in results[0]["error"].lower()


@pytest.mark.asyncio
async def test_drop_multiple_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Dropping multiple valid seats in one call succeeds for all."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 3)

    students = [
        {
            "student_id": f"stu-{uuid4().hex[:8]}",
            "email": f"{uuid4().hex[:8]}@uni.org",
        }
        for _ in range(3)
    ]
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": students},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_ids = [r["seat_id"] for r in assign_resp.json()["results"]]
    assert len(seat_ids) == 3

    with mock_drop_deps():
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": seat_ids},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 3
    for r in results:
        assert r["drop_successful"] is True
        assert r["error"] is None


@pytest.mark.asyncio
async def test_drop_seats_mixed_valid_and_invalid(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Mix of valid, unassigned, and nonexistent seats — each gets correct result."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    assigned_seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Get the unassigned seat
    list_resp = await async_test_client.get(
        f"/seats/courses/{course_id}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    all_seats = list_resp.json()["seats"]
    unassigned_seat_id = next(s["id"] for s in all_seats if s["enrolment_id"] is None)

    nonexistent_seat_id = str(uuid4())

    with mock_drop_deps():
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={
                "seat_ids": [assigned_seat_id, unassigned_seat_id, nonexistent_seat_id]
            },
            headers=headers,
        )

    assert drop_resp.status_code == 200
    results = drop_resp.json()["results"]
    assert len(results) == 3

    result_map = {r["seat_id"]: r for r in results}

    assert result_map[assigned_seat_id]["drop_successful"] is True
    assert result_map[unassigned_seat_id]["drop_successful"] is False
    assert "no enrolment" in result_map[unassigned_seat_id]["error"].lower()
    assert result_map[nonexistent_seat_id]["drop_successful"] is False
    assert "not found" in result_map[nonexistent_seat_id]["error"].lower()


@pytest.mark.asyncio
async def test_drop_seats_low_balance_consumes_seat(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If student balance < CREDITS_PER_SEAT - 50, seat is consumed even on early drop."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    # Mock deplete returning 100 (below 150 threshold) — seat should be consumed
    with (
        patch(
            "virtual_labs.usecases.course.drop_seats._clear_project_groups",
            new_callable=AsyncMock,
        ),
        patch(
            "virtual_labs.usecases.course.drop_seats.accounting_cases.deplete_project_budget",
            new_callable=AsyncMock,
            return_value=100.0,
        ),
    ):
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )

    assert drop_resp.status_code == 200
    assert drop_resp.json()["results"][0]["drop_successful"] is True

    # Verify seat is consumed (not available for reassignment)
    list_resp = await async_test_client.get(
        f"/seats/courses/{course_id}",
        headers=headers,
    )
    seat = next(s for s in list_resp.json()["seats"] if s["id"] == seat_id)
    assert seat["is_consumed"] is True


@pytest.mark.asyncio
async def test_drop_seats_previously_dropped_consumes_seat(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A seat that was already recovered once gets consumed on second assignment + drop."""
    headers = get_headers()
    course_id = course_for_seats

    await provision_seats(async_test_client, course_id, 1)

    # First student assignment
    student1 = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student1]},
            headers=headers,
        )
    assert assign_resp.status_code == 200
    seat_id = assign_resp.json()["results"][0]["seat_id"]

    # First drop (early, sufficient balance) — seat should be released
    with mock_drop_deps():
        drop_resp = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )
    assert drop_resp.status_code == 200
    assert drop_resp.json()["results"][0]["drop_successful"] is True

    # Verify seat is NOT consumed (released for reassignment)
    list_resp = await async_test_client.get(
        f"/seats/courses/{course_id}",
        headers=headers,
    )
    seat = next(s for s in list_resp.json()["seats"] if s["id"] == seat_id)
    assert seat["is_consumed"] is False
    assert seat["previously_dropped"] is True
    assert seat["enrolment_id"] is None

    # Second student assignment to the same seat
    student2 = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    with mock_assign_deps():
        assign_resp2 = await async_test_client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": [student2]},
            headers=headers,
        )
    assert assign_resp2.status_code == 200
    # Should reuse the same seat (only one available)
    seat_id2 = assign_resp2.json()["results"][0]["seat_id"]
    assert seat_id2 == seat_id

    # Second drop — seat was previously dropped, so it should be consumed
    with mock_drop_deps():
        drop_resp2 = await async_test_client.post(
            f"/seats/courses/{course_id}/drop",
            json={"seat_ids": [seat_id]},
            headers=headers,
        )
    assert drop_resp2.status_code == 200
    assert drop_resp2.json()["results"][0]["drop_successful"] is True

    # Verify seat is now consumed
    list_resp2 = await async_test_client.get(
        f"/seats/courses/{course_id}",
        headers=headers,
    )
    seat = next(s for s in list_resp2.json()["seats"] if s["id"] == seat_id)
    assert seat["is_consumed"] is True
