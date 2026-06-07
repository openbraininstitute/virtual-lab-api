"""Shared fixtures and helpers for course tests."""

from typing import AsyncGenerator
from unittest.mock import patch
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from virtual_labs.infrastructure.db.models import Course, Institution, VirtualLab
from virtual_labs.infrastructure.settings import settings
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab_with_project,
    get_headers,
    session_context_factory,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def _get_or_create_institution() -> str:
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
    async with session_context_factory() as session:
        await session.execute(delete(Course).where(Course.id == UUID(course_id)))
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await _get_or_create_institution()


@pytest_asyncio.fixture
async def draft_course(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[tuple[str, str], None]:
    """Create a course in draft status and return (course_id, vlab_id)."""
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
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post("/courses", json=body, headers=headers)

    assert response.status_code == 200
    course_id = response.json()["data"]["id"]

    yield course_id, lab_id

    await _cleanup_course(course_id)
    await cleanup_resources(async_test_client, lab_id)
