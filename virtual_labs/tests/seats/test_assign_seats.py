"""Tests for the assign-seats endpoint (POST /courses/{course_id}/assign_seats)."""

from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.utils import (
    get_headers,
)


def _assign_payload(students: list[dict] | None = None) -> dict:
    if students is None:
        students = [
            {
                "student_id": f"student-{uuid4().hex[:8]}",
                "email": f"{uuid4().hex[:8]}@test.org",
            }
        ]
    return {"students": students}


@dataclass
class AccountingMocks:
    """Holds mocks exposed by mock_assign_accounting."""

    balance: MagicMock
    transfer: MagicMock


@contextmanager
def mock_assign_accounting(
    accounting_url: str | None = "http://accounting:8000",
):
    """Patch accounting dependencies for the assign-seats flow.

    Yields an AccountingMocks instance with .balance and .transfer mocks
    (only available when accounting_url is not None).
    """
    with (
        patch(
            "virtual_labs.usecases.project.create_new_project.ensure_accounting_initialization",
            new_callable=AsyncMock,
        ),
        patch(
            "virtual_labs.usecases.course.assign_seats.settings.ACCOUNTING_BASE_URL",
            accounting_url,
        ),
        patch(
            "virtual_labs.usecases.course.assign_seats.accounting_cases.get_virtual_lab_balance"
        ) as mock_balance,
        patch(
            "virtual_labs.usecases.course.assign_seats.accounting_cases.assign_project_budget"
        ) as mock_transfer,
    ):
        yield AccountingMocks(balance=mock_balance, transfer=mock_transfer)


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Assign a single seat — project created, credit transfer succeeds."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=1000.0))
        mocks.transfer.return_value = AsyncMock()
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is True
    assert results[0]["seat_id"] is not None
    assert results[0]["project_id"] is not None
    assert results[0]["student_id"] == student["student_id"]
    assert results[0]["email"] == student["email"]


@pytest.mark.asyncio
async def test_assign_seats_multiple_students(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Assign multiple seats in one call."""
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
    body = _assign_payload(students)

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=5000.0))
        mocks.transfer.return_value = AsyncMock()
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert all(r["assignment_successful"] for r in results)
    assert all(r["credit_transferred"] for r in results)
    assert all(r["seat_id"] is not None for r in results)
    project_ids = [r["project_id"] for r in results]
    assert len(set(project_ids)) == 3
    seat_ids = [r["seat_id"] for r in results]
    assert len(set(seat_ids)) == 3


@pytest.mark.asyncio
async def test_assign_seats_credit_transfer_fails_gracefully(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If credit transfer fails, seat is still assigned but credit_transferred=False."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=1000.0))
        mocks.transfer.side_effect = Exception("accounting down")
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is False
    assert results[0]["project_id"] is not None


@pytest.mark.asyncio
async def test_assign_seats_no_accounting_url(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """When ACCOUNTING_BASE_URL is None, assignment succeeds but no transfer."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting(accounting_url=None):
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is False


@pytest.mark.asyncio
async def test_assign_seats_partial_credit(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """When balance < seat credit, transfers what's available (partial)."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=50.0))
        mocks.transfer.return_value = AsyncMock()
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is True
    assert results[0]["credit_transferred_amount"] == 50.0
    assert "Partial credit" in results[0]["error"]


@pytest.mark.asyncio
async def test_assign_seats_zero_balance_skips_transfer(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """When balance is 0, no transfer is attempted."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting() as mocks:
        mocks.balance.return_value = AsyncMock(data=AsyncMock(balance=0.0))
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is False
    assert results[0]["credit_transferred_amount"] == 0
    mocks.transfer.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_seats_fails_for_draft_course(
    async_test_client: AsyncClient,
    draft_course_for_seats: str,
) -> None:
    """Cannot assign seats to a draft course."""
    headers = get_headers()
    body = _assign_payload()

    response = await async_test_client.post(
        f"/courses/{draft_course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 409
    assert "draft" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_assign_seats_fails_for_voided_course(
    async_test_client: AsyncClient,
    voided_course_for_seats: str,
) -> None:
    """Cannot assign seats to a voided course."""
    headers = get_headers()
    body = _assign_payload()

    response = await async_test_client.post(
        f"/courses/{voided_course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 409
    assert "voided" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_assign_seats_fails_not_enough_seats(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Fails when requesting more seats than available."""
    headers = get_headers()
    students = [
        {
            "student_id": f"stu-{uuid4().hex[:8]}",
            "email": f"{uuid4().hex[:8]}@uni.org",
        }
        for _ in range(5)
    ]
    body = _assign_payload(students)

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 409
    assert "not enough" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_assign_seats_fails_nonexistent_course(
    async_test_client: AsyncClient,
) -> None:
    """Returns 403 for a nonexistent course (verify_course_admin fails)."""
    headers = get_headers()
    body = _assign_payload()

    response = await async_test_client.post(
        f"/courses/{uuid4()}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assign_seats_rejects_duplicate_student_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Duplicate student_id in request is rejected by validation."""
    headers = get_headers()
    student_id = f"stu-{uuid4().hex[:8]}"
    students = [
        {"student_id": student_id, "email": f"{uuid4().hex[:8]}@uni.org"},
        {"student_id": student_id, "email": f"{uuid4().hex[:8]}@uni.org"},
    ]
    body = _assign_payload(students)

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assign_seats_rejects_duplicate_emails(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Duplicate email in request is rejected by validation."""
    headers = get_headers()
    email = f"{uuid4().hex[:8]}@uni.org"
    students = [
        {"student_id": f"stu-{uuid4().hex[:8]}", "email": email},
        {"student_id": f"stu-{uuid4().hex[:8]}", "email": email},
    ]
    body = _assign_payload(students)

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assign_seats_rejects_empty_students_list(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Empty students list is rejected by validation (min_length=1)."""
    headers = get_headers()
    body = {"students": []}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assign_seats_mixed_outcomes(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Multiple students: first gets full credit, second partial, third zero balance."""
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
    body = _assign_payload(students)

    # Simulate decreasing balance: 1000 → 50 → 0
    balance_responses = [
        AsyncMock(data=AsyncMock(balance=1000.0)),
        AsyncMock(data=AsyncMock(balance=50.0)),
        AsyncMock(data=AsyncMock(balance=0.0)),
    ]

    with mock_assign_accounting() as mocks:
        mocks.balance.side_effect = balance_responses
        mocks.transfer.return_value = AsyncMock()
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3

    # First: full credit (balance=1000, seat_credit=200)
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred"] is True
    assert results[0]["credit_transferred_amount"] == 200.0
    assert results[0]["error"] is None

    # Second: partial credit (balance=50, seat_credit=200)
    assert results[1]["assignment_successful"] is True
    assert results[1]["credit_transferred"] is True
    assert results[1]["credit_transferred_amount"] == 50.0
    assert "Partial credit" in results[1]["error"]

    # Third: zero balance — no transfer attempted
    assert results[2]["assignment_successful"] is True
    assert results[2]["credit_transferred"] is False
    assert results[2]["credit_transferred_amount"] == 0
    assert results[2]["error"] is None


@pytest.mark.asyncio
async def test_assign_seats_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A user who is not a vlab admin cannot assign seats."""
    headers = get_headers("test-1")  # different user, not admin of this lab
    body = _assign_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/assign_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403
