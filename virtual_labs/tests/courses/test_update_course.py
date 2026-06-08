"""Tests for the update-course endpoint (PATCH /courses/{course_id})."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.courses.conftest import (
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)
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
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01T00:00:00Z",
                "end_date": "2026-12-15T00:00:00Z",
                "last_drop_date": "2026-09-14T00:00:00Z",
            },
            headers=headers,
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
    """Sending only one field should update only that field."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2026-09-01T00:00:00Z"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01T00:00:00Z"
    assert data["end_date"] is None
    assert data["last_drop_date"] is None


@pytest.mark.asyncio
async def test_update_draft_course_institution(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
    institution_id: str,
) -> None:
    """Can update institution_id on a draft course."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"institution_id": institution_id},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["data"]["institution_id"] == institution_id


# ──────────────────────────────────────────────────────────────────────
# Immutability tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_active_course_fails(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Active courses cannot be updated."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Set dates and activate
        await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01T00:00:00Z",
                "end_date": "2026-12-15T00:00:00Z",
                "last_drop_date": "2026-09-14T00:00:00Z",
            },
            headers=headers,
        )
        await async_test_client.post(f"/courses/{course_id}/activate", headers=headers)

        # Try to update
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2027-01-01T00:00:00Z"},
            headers=headers,
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_voided_course_fails(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Voided courses cannot be updated."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Void the course
        await async_test_client.post(f"/courses/{course_id}/void", headers=headers)

        # Try to update
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2027-01-01T00:00:00Z"},
            headers=headers,
        )

    assert response.status_code == 409


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{uuid4()}",
            json={"start_date": "2026-09-01T00:00:00Z"},
            headers=headers,
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

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2026-09-01T00:00:00Z"},
            headers=headers,
        )

    assert response.status_code == 403
