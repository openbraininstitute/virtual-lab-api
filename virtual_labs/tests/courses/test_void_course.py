"""Tests for the void-course endpoint (POST /courses/{course_id}/void)."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.infrastructure.db.models import Course, CourseEnrolment
from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.seats.helpers import provision_seats
from virtual_labs.tests.seats.test_drop_seats import mock_assign_deps, mock_drop_deps
from virtual_labs.tests.utils import get_headers, session_context_factory


@contextmanager
def mock_void_deps():
    """Mock all external deps needed by void_course (drop + vlab depletion)."""
    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.update_course_status.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        yield


async def _set_course_dates(async_test_client: AsyncClient, course_id: str) -> None:
    """Set all required dates on a draft course so it can be activated."""
    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-12-15T00:00:00Z",
            "last_drop_date": "2026-09-14T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    assert response.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_void_draft_course_successfully(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    with mock_void_deps():
        response = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == course_id
    assert data["status"] == "voided"


@pytest.mark.asyncio
async def test_void_active_course_successfully(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    await _set_course_dates(async_test_client, course_id)

    # First activate
    await async_test_client.post(
        f"/courses/{course_id}/activate", headers=SERVICE_ADMIN_HEADERS
    )
    # Then void
    with mock_void_deps():
        response = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "voided"


@pytest.mark.asyncio
async def test_void_course_is_idempotent(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Voiding an already-voided course succeeds (idempotent)."""
    course_id, _ = draft_course

    with mock_void_deps():
        # Void first time
        await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )
        # Void again — should still succeed
        response = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "voided"


# ──────────────────────────────────────────────────────────────────────
# Drop & budget depletion tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_void_course_drops_all_enrolments(
    async_test_client: AsyncClient,
    course_for_seats: str,
) -> None:
    """Voiding a course drops every undropped enrolment."""
    client = async_test_client
    course_id = course_for_seats

    # Provision and assign seats
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
    enrolment_ids = [r["enrolment_id"] for r in assign_resp.json()["results"]]

    # Void the course
    with mock_void_deps():
        void_resp = await client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )
    assert void_resp.status_code == 200
    assert void_resp.json()["data"]["status"] == "voided"

    # Assert all enrolments are dropped
    async with session_context_factory() as session:
        for eid in enrolment_ids:
            enrolment = await session.get(CourseEnrolment, UUID(eid))
            assert enrolment is not None
            assert enrolment.is_dropped is True


@pytest.mark.asyncio
async def test_void_course_depletes_vlab_budget(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Voiding a course sets budget_depleted to True."""
    course_id, _ = draft_course

    with mock_void_deps():
        response = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200

    async with session_context_factory() as session:
        course = await session.get(Course, UUID(course_id))
        assert course is not None
        assert course.budget_depleted is True


@pytest.mark.asyncio
async def test_void_course_depletion_failure_still_voids(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """If vlab budget depletion fails, course is still voided (budget_depleted stays False)."""
    course_id, _ = draft_course

    with (
        mock_drop_deps(),
        patch(
            "virtual_labs.usecases.course.update_course_status.accounting_cases.deplete_vlab_budget",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        response = await async_test_client.post(
            f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "voided"

    async with session_context_factory() as session:
        course = await session.get(Course, UUID(course_id))
        assert course is not None
        assert course.budget_depleted is False


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_void_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.post(
        f"/courses/{uuid4()}/void", headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_void_course_fails_without_auth(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/void",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_void_course_fails_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    response = await async_test_client.post(
        f"/courses/{course_id}/void", headers=headers
    )

    assert response.status_code == 403
