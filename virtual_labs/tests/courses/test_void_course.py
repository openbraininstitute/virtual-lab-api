"""Tests for the void-course endpoint (POST /courses/{course_id}/void)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import get_headers


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
