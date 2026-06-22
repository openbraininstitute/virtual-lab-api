"""Tests for the assign-seats endpoint (POST /seats/courses/{course_id}/assign)."""

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.utils import get_headers


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
def mock_assign_accounting(fund_succeeds: bool = True, patch_email: bool = True):
    """Patch accounting + project creation dependencies for the assign-seats flow.

    fund_succeeds: whether fund_project returns True or False.
    patch_email: whether to also patch send_enrolment_claim_email (default: True).
    """
    patches = [
        patch(
            "virtual_labs.usecases.project.create_new_project.ensure_accounting_initialization",
            new_callable=AsyncMock,
        ),
        patch(
            "virtual_labs.usecases.course.assign_seats.accounting_cases.fund_project",
            new_callable=AsyncMock,
            return_value=fund_succeeds,
        ),
    ]
    if patch_email:
        patches.append(
            patch(
                "virtual_labs.usecases.course.assign_seats.send_enrolment_claim_email",
                new_callable=AsyncMock,
            )
        )

    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        yield mocks[1]  # the fund_project mock


@contextmanager
def mock_enrolment_email(succeed: bool = True):
    """Patch send_enrolment_claim_email. Yields the AsyncMock."""
    with patch(
        "virtual_labs.usecases.course.assign_seats.send_enrolment_claim_email",
        new_callable=AsyncMock,
    ) as mock_email:
        if not succeed:
            mock_email.side_effect = Exception("SES unavailable")
        yield mock_email


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assign_seats_success(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Assign a single seat — project created, funded, enrolment created."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 2)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting(fund_succeeds=True):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["assignment_successful"] is True
    assert results[0]["credit_transferred_amount"] == 200.0
    assert results[0]["project_id"] is not None
    assert results[0]["enrolment_id"] is not None
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

    with mock_assign_accounting(fund_succeeds=True):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert all(r["assignment_successful"] for r in results)
    assert all(r["credit_transferred_amount"] == 200.0 for r in results)
    project_ids = [r["project_id"] for r in results]
    assert len(set(project_ids)) == 3
    enrolment_ids = [r["enrolment_id"] for r in results]
    assert len(set(enrolment_ids)) == 3


@pytest.mark.asyncio
async def test_assign_seats_funding_fails_rolls_back(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If fund_project fails, assignment fails and project is soft-deleted."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with mock_assign_accounting(fund_succeeds=False):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["assignment_successful"] is False
    assert results[0]["error"] is not None


@pytest.mark.asyncio
async def test_assign_seats_email_failure_does_not_rollback(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If claim email fails, enrolment and project are still created but email_sent=False."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with (
        mock_assign_accounting(fund_succeeds=True, patch_email=False),
        mock_enrolment_email(succeed=False),
    ):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["assignment_successful"] is True
    assert results[0]["enrolment_id"] is not None
    assert results[0]["project_id"] is not None
    assert results[0]["email_sent"] is False


@pytest.mark.asyncio
async def test_assign_seats_claim_email_sent(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Claim email is sent after successful assignment."""
    headers = get_headers()
    course_id = course_for_seats
    await provision_seats(async_test_client, course_id, 1)

    student = {
        "student_id": f"stu-{uuid4().hex[:8]}",
        "email": f"{uuid4().hex[:8]}@uni.org",
    }
    body = _assign_payload([student])

    with (
        mock_assign_accounting(fund_succeeds=True, patch_email=False),
        mock_enrolment_email() as mock_email,
    ):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["email_sent"] is True
    mock_email.assert_awaited_once()


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
        f"/seats/courses/{draft_course_for_seats}/assign",
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
        f"/seats/courses/{voided_course_for_seats}/assign",
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
        f"/seats/courses/{course_for_seats}/assign",
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
        f"/seats/courses/{uuid4()}/assign",
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
        f"/seats/courses/{course_for_seats}/assign",
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
        f"/seats/courses/{course_for_seats}/assign",
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
        f"/seats/courses/{course_for_seats}/assign",
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
    with mock_assign_accounting(fund_succeeds=True):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )
    assert response.status_code == 200

    # Second assignment with same student fails
    with mock_assign_accounting(fund_succeeds=True):
        response = await async_test_client.post(
            f"/seats/courses/{course_id}/assign", json=body, headers=headers
        )
    assert response.status_code == 409
    assert "already enrolled" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_assign_seats_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """A user who is not a vlab admin cannot assign seats."""
    headers = get_headers("test-1")
    body = _assign_payload()

    response = await async_test_client.post(
        f"/seats/courses/{course_for_seats}/assign",
        json=body,
        headers=headers,
    )

    assert response.status_code == 403
