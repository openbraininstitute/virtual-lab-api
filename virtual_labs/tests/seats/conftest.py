"""Shared fixtures for seat tests.

Re-uses shared helpers since seats require a course-enabled virtual lab.
"""

from typing import AsyncGenerator
from unittest.mock import patch
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, update

from virtual_labs.infrastructure.db.models import Seat, VirtualLab
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.utils import (
    cleanup_course,
    cleanup_resources,
    create_mock_lab_with_project,
    get_headers,
    get_or_create_institution,
    mock_admin_userinfo,
    session_context_factory,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def cleanup_seats(vlab_id: str) -> None:
    async with session_context_factory() as session:
        await session.execute(delete(Seat).where(Seat.virtual_lab_id == UUID(vlab_id)))
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await get_or_create_institution()


@pytest_asyncio.fixture
async def vlab_with_course(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Create a virtual lab with a course. Returns the vlab_id."""
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

    # Create a course for this vlab
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

    yield lab_id

    await cleanup_seats(lab_id)
    await cleanup_course(course_id)
    await cleanup_resources(async_test_client, lab_id)


@pytest_asyncio.fixture
async def vlab_without_course(
    async_test_client: AsyncClient,
) -> AsyncGenerator[str, None]:
    """Create a virtual lab WITHOUT a course. Returns the vlab_id."""
    lab_data, _ = await create_mock_lab_with_project(async_test_client)
    lab_id = lab_data["id"]

    yield lab_id

    await cleanup_resources(async_test_client, lab_id)
