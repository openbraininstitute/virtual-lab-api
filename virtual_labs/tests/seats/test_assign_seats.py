"""Tests for the assign-seats endpoint (POST /courses/{course_id}/assign_seats)."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
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


@contextmanager
def mock_claim_email(succeed: bool = True):
    """Patch the send_enrolment_claim_email call.

    When succeed=True the mock resolves normally.
    When succeed=False it raises an exception.
    """
    with patch(
        "virtual_labs.usecases.course.assign_seats.send_enrolment_claim_email",
        new_callable=AsyncMock,
    ) as mock_send:
        if not succeed:
            mock_send.side_effect = Exception("SES unavailable")
        yield mock_send


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Assign a single seat — enrolment created, email sent."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_claim_email() as mock_send:
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["seat_id"] is not None
    assert results[0]["enrolment_id"] is not None
    assert results[0]["email_sent"] is True
    assert results[0]["student_id"] == student["student_id"]
    assert results[0]["email"] == student["email"]
    mock_send.assert_awaited_once()


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

    with mock_claim_email() as mock_send:
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert all(r["email_sent"] for r in results)
    assert all(r["seat_id"] is not None for r in results)
    assert all(r["enrolment_id"] is not None for r in results)
    seat_ids = [r["seat_id"] for r in results]
    assert len(set(seat_ids)) == 3
    enrolment_ids = [r["enrolment_id"] for r in results]
    assert len(set(enrolment_ids)) == 3
    assert mock_send.await_count == 3


@pytest.mark.asyncio
async def test_assign_seats_email_failure_does_not_rollback(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If email fails, enrolment is still created but email_sent=False."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_claim_email(succeed=False):
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["enrolment_id"] is not None
    assert results[0]["seat_id"] is not None
    assert results[0]["email_sent"] is False


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
async def test_assign_seats_duplicate_enrolment_rejected(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Assigning the same student twice to a course returns 409."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    # First assignment succeeds
    with mock_claim_email():
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )
    assert response.status_code == 200

    # Second assignment with same student fails
    with mock_claim_email():
        response = await async_test_client.post(
            f"/courses/{course_id}/assign_seats", json=body, headers=headers
        )
    assert response.status_code == 409
    assert "already enrolled" in response.json()["message"].lower()


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
