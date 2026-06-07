"""Tests for the update-course endpoint (PATCH /courses/{course_id})."""

from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from virtual_labs.infrastructure.db.models import Course
from virtual_labs.infrastructure.settings import settings
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import (
    create_mock_lab_with_project,
    get_headers,
    session_context_factory,
)


def _mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def _mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def _get_or_create_institution() -> str:
    from virtual_labs.infrastructure.db.models import Institution

    async with session_context_factory() as session:
        result = await session.scalar(
            select(Institution.id).where(Institution.name == "Open Brain Institute")
        )
        if result:
            return str(result)

        institution = Institution(
            name="Open Brain Institute",
            contact_email="obi-virtual-lab@openbraininstitute.org",
        )
        session.add(institution)
        await session.commit()
        await session.refresh(institution)
        return str(institution.id)


async def _cleanup_course(course_id: str) -> None:
    from uuid import UUID

    async with session_context_factory() as session:
        await session.execute(delete(Course).where(Course.id == UUID(course_id)))
        await session.commit()


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await _get_or_create_institution()


@pytest_asyncio.fixture
async def draft_course(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[tuple[str, str], None]:
    """Create a course in draft status and return (course_id, vlab_id)."""
    from uuid import UUID

    from sqlalchemy import update

    from virtual_labs.infrastructure.db.models import VirtualLab
    from virtual_labs.tests.utils import cleanup_resources

    lab_data, project_id = await create_mock_lab_with_project(async_test_client)
    lab_id = lab_data["id"]

    # Mark as course lab
    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    headers = get_headers()
    body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 200
    course_id = response.json()["data"]["id"]

    yield course_id, lab_id

    await _cleanup_course(course_id)
    await cleanup_resources(async_test_client, lab_id)


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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01",
                "end_date": "2026-12-15",
                "last_drop_date": "2026-10-01",
            },
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01"
    assert data["end_date"] == "2026-12-15"
    assert data["last_drop_date"] == "2026-10-01"


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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2026-09-01"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01"
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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        # Set dates and activate
        await async_test_client.patch(
            f"/courses/{course_id}",
            json={
                "start_date": "2026-09-01",
                "end_date": "2026-12-15",
                "last_drop_date": "2026-10-01",
            },
            headers=headers,
        )
        await async_test_client.post(f"/courses/{course_id}/activate", headers=headers)

        # Try to update
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2027-01-01"},
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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        # Void the course
        await async_test_client.post(f"/courses/{course_id}/void", headers=headers)

        # Try to update
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2027-01-01"},
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
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{uuid4()}",
            json={"start_date": "2026-09-01"},
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
        json={"start_date": "2026-09-01"},
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
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.patch(
            f"/courses/{course_id}",
            json={"start_date": "2026-09-01"},
            headers=headers,
        )

    assert response.status_code == 403
