"""Tests for the activate-course endpoint (POST /courses/{course_id}/activate)."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import (
    get_headers,
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)


async def _set_course_dates(async_test_client: AsyncClient, course_id: str) -> None:
    """Set all required dates on a draft course so it can be activated."""
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


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_course_successfully(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    await _set_course_dates(async_test_client, course_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == course_id
    assert data["status"] == "active"


# ──────────────────────────────────────────────────────────────────────
# Error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_course_fails_when_dates_missing(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Cannot activate a course without all dates set."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409
    assert "not set" in response.json()["message"]


@pytest.mark.asyncio
async def test_activate_course_fails_with_partial_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Cannot activate if only some dates are set."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Set only start_date
        await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2026-09-01T00:00:00Z"},
            headers=headers,
        )
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409
    msg = response.json()["message"]
    assert "end_date" in msg
    assert "last_drop_date" in msg


@pytest.mark.asyncio
async def test_activate_course_fails_with_unordered_dates(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Cannot activate if dates don't satisfy start_date < last_drop_date < end_date."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Set dates in wrong order: end_date before last_drop_date
        await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01T00:00:00Z",
                "end_date": "2026-09-10T00:00:00Z",
                "last_drop_date": "2026-12-15T00:00:00Z",
            },
            headers=headers,
        )
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409
    assert "start_date < last_drop_date < end_date" in response.json()["message"]


@pytest.mark.asyncio
async def test_activate_course_fails_when_last_drop_date_exceeds_two_weeks(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Cannot activate if last_drop_date is more than 2 weeks after start_date."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # last_drop_date is 15 days after start_date (exceeds 2 weeks)
        await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01T00:00:00Z",
                "end_date": "2026-12-15T00:00:00Z",
                "last_drop_date": "2026-09-16T00:00:00Z",
            },
            headers=headers,
        )
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409
    assert "within 2 weeks" in response.json()["message"]


@pytest.mark.asyncio
async def test_activate_course_fails_when_already_active(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    await _set_course_dates(async_test_client, course_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Activate first
        await async_test_client.post(f"/courses/{course_id}/activate", headers=headers)
        # Try to activate again
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_activate_course_fails_when_voided(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        # Void first
        await async_test_client.post(f"/courses/{course_id}/void", headers=headers)
        # Try to activate
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_activate_course_not_found(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            f"/courses/{uuid4()}/activate", headers=headers
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_activate_course_fails_without_auth(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.post(
        f"/courses/{course_id}/activate",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_activate_course_fails_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.post(
            f"/courses/{course_id}/activate", headers=headers
        )

    assert response.status_code == 403
