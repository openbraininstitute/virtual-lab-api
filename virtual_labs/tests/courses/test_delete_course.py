"""Tests for the delete-course endpoint (DELETE /courses/{course_id})."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment, Seat
from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_drop_seats import mock_assign_deps, mock_drop_deps
from virtual_labs.tests.utils import get_headers, session_context_factory


@contextmanager
def patch_void_externals():
    """Patch external services called by void_course (drop seats + vlab budget depletion)."""
    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.update_course_status.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=200.0,
        ),
    ):
        yield


@contextmanager
def mock_delete_deps():
    """Mock all external deps needed by delete_course (drop + vlab depletion)."""
    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.delete_course.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=200.0,
        ),
    ):
        yield


# ──────────────────────────────────────────────────────────────────────
# Auth tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_course_fails_without_auth(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    course_id = course_for_seats

    response = await async_test_client.delete(
        f"/courses/{course_id}",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_course_fails_for_non_service_admin(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    course_id = course_for_seats

    response = await async_test_client.delete(
        f"/courses/{course_id}", headers=get_headers()
    )

    assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Not found
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.delete(
        f"/courses/{uuid4()}", headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# Status restriction — only draft and voided courses can be deleted
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_active_course_fails_with_conflict(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Active courses cannot be deleted — must be voided first."""
    course_id = course_for_seats

    with mock_delete_deps():
        response = await async_test_client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 409

    async with session_context_factory() as session:
        assert await session.get(Course, UUID(course_id)) is not None


@pytest.mark.asyncio
async def test_delete_draft_course_successfully(
    async_test_client: AsyncClient,
    draft_course_for_seats: str,
) -> None:
    course_id = draft_course_for_seats

    with mock_delete_deps():
        response = await async_test_client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Course deleted successfully"

    async with session_context_factory() as session:
        assert await session.get(Course, UUID(course_id)) is None


@pytest.mark.asyncio
async def test_delete_voided_course_successfully(
    async_test_client: AsyncClient,
    voided_course_for_seats: str,
) -> None:
    course_id = voided_course_for_seats

    with mock_delete_deps():
        response = await async_test_client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Course deleted successfully"

    async with session_context_factory() as session:
        assert await session.get(Course, UUID(course_id)) is None


# ──────────────────────────────────────────────────────────────────────
# Happy path — no enrolments
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_course_removes_seats(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Seats are hard-deleted along with the course."""
    course_id = course_for_seats

    prov = await provision_seats(async_test_client, course_id, 3)
    seat_ids = [UUID(s["id"]) for s in prov["seats"]]

    with patch_void_externals():
        void_resp = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )
    assert void_resp.status_code == 200

    with mock_delete_deps():
        response = await async_test_client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200

    async with session_context_factory() as session:
        for seat_id in seat_ids:
            assert await session.get(Seat, seat_id) is None
        assert await session.get(Course, UUID(course_id)) is None


# ──────────────────────────────────────────────────────────────────────
# Happy path — with enrolments
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_course_drops_enrolments_and_removes_rows(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """All enrolments are dropped and then hard-deleted with the course."""
    client = async_test_client
    course_id = course_for_seats

    await provision_seats(client, course_id, 2)
    students = [
        {"student_id": f"stu-{uuid4().hex[:8]}", "email": f"{uuid4().hex[:8]}@u.org"},
        {"student_id": f"stu-{uuid4().hex[:8]}", "email": f"{uuid4().hex[:8]}@u.org"},
    ]
    with mock_assign_deps():
        assign_resp = await client.post(
            f"/seats/courses/{course_id}/assign",
            json={"students": students},
            headers=get_headers(),
        )
    assert assign_resp.status_code == 200
    enrolment_ids = [UUID(r["enrolment_id"]) for r in assign_resp.json()["results"]]

    with patch_void_externals():
        void_resp = await client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )
    assert void_resp.status_code == 200

    with mock_delete_deps():
        response = await client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200

    async with session_context_factory() as session:
        assert await session.get(Course, UUID(course_id)) is None
        for eid in enrolment_ids:
            assert await session.get(CourseEnrolment, eid) is None


# ──────────────────────────────────────────────────────────────────────
# Strict failure — budget depletion fails → course not deleted
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_course_aborts_if_budget_depletion_fails(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """If vlab budget depletion fails, the course must NOT be deleted."""
    course_id = course_for_seats

    # Void first (budget depletion intentionally fails → budget_depleted stays False)
    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.update_course_status.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        void_resp = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )
    assert void_resp.status_code == 200

    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.delete_course.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await async_test_client.delete(
            f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 502

    async with session_context_factory() as session:
        assert await session.get(Course, UUID(course_id)) is not None
