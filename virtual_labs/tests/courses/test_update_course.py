"""Tests for the update-course endpoint (PATCH /courses/{course_id})."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import get_headers

# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_draft_course_all_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

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
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01T00:00:00Z"
    assert data["end_date"] == "2026-12-15T00:00:00Z"
    assert data["last_drop_date"] == "2026-09-14T00:00:00Z"


@pytest.mark.asyncio
async def test_update_draft_course_partial(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Sending only one field should update only that field, leaving the rest."""
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"last_drop_date": "2026-10-01T00:00:00Z"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["last_drop_date"] == "2026-10-01T00:00:00Z"
    # Unchanged from the draft_course fixture.
    assert data["start_date"] == "2026-09-01T00:00:00Z"
    assert data["end_date"] == "2026-12-15T00:00:00Z"


@pytest.mark.asyncio
async def test_update_course_rejects_null_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """The date columns are NOT NULL, so an explicit null is rejected."""
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"start_date": None},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_draft_course_institution(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
    institution_id: str,
) -> None:
    """Can update institution_id on a draft course."""
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"institution_id": institution_id},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"]["institution_id"] == institution_id


# ──────────────────────────────────────────────────────────────────────
# Status-independent update tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_active_course_succeeds(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Active courses can be updated (as long as date ordering stays valid)."""
    course_id, _ = draft_course

    # Set dates and activate
    await async_test_client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-12-15T00:00:00Z",
            "last_drop_date": "2026-09-14T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    await async_test_client.post(
        f"/courses/{course_id}/activate", headers=SERVICE_ADMIN_HEADERS
    )

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"end_date": "2027-01-15T00:00:00Z"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"]["end_date"] == "2027-01-15T00:00:00Z"


@pytest.mark.asyncio
async def test_update_voided_course_succeeds(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Voided courses can be updated."""
    course_id, _ = draft_course

    await async_test_client.post(
        f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
    )

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2027-01-01T00:00:00Z",
            "last_drop_date": "2027-01-14T00:00:00Z",
            "end_date": "2027-03-15T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_course_rejects_unordered_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """The same date checks as activation apply to updates."""
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-09-10T00:00:00Z",
            "last_drop_date": "2026-12-15T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert "start_date < last_drop_date < end_date" in response.json()["message"]


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.patch(
        f"/courses/{uuid4()}",
        json={"start_date": "2026-09-01T00:00:00Z"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_course_fails_without_auth(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"start_date": "2026-09-01T00:00:00Z"},
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_course_fails_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    response = await async_test_client.patch(
        f"/courses/{course_id}",
        json={"start_date": "2026-09-01T00:00:00Z"},
        headers=headers,
    )

    assert response.status_code == 403
