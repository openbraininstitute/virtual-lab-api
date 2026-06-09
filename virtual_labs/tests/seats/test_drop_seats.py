"""Tests for the drop-seats endpoint (POST /courses/{course_id}/drop_seats)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers


def _drop_payload(student_ids: list[str] | None = None) -> dict:
    if student_ids is None:
        student_ids = [f"student-{uuid4().hex[:8]}"]
    return {"student_ids": student_ids}


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
async def test_drop_seats_rejects_empty_student_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Empty student_ids list is rejected by validation."""
    headers = get_headers()
    body = {"student_ids": []}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_drop_seats_rejects_duplicate_student_ids(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Duplicate student_id in request is rejected by validation."""
    headers = get_headers()
    student_id = f"stu-{uuid4().hex[:8]}"
    body = {"student_ids": [student_id, student_id]}

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Usecase call (currently raises NotImplementedError → 500)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drop_seats_reaches_usecase(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Vlab admin can reach the usecase (currently returns 500 since not implemented)."""
    headers = get_headers()  # "test" user is the lab owner/admin
    body = _drop_payload()

    response = await async_test_client.post(
        f"/courses/{course_for_seats}/drop_seats",
        json=body,
        headers=headers,
    )

    # The usecase raises NotImplementedError → FastAPI returns 500
    assert response.status_code == 500
