"""Shared fixtures and helpers for course tests."""

from typing import AsyncGenerator
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.utils import (
    cleanup_course,
    cleanup_resources,
    create_mock_lab_with_project,
    get_headers,
    get_or_create_institution,
    session_context_factory,
)

SERVICE_ADMIN_HEADERS = get_headers("test-service-admin")

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await get_or_create_institution()


@pytest_asyncio.fixture
async def vlab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, str], None]:
    """Create a course-eligible virtual lab + project. Returns (vlab_id, project_id)."""
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

    yield lab_id, project_id

    await cleanup_resources(async_test_client, lab_id)


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

    body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }

    response = await async_test_client.post(
        "/courses", json=body, headers=SERVICE_ADMIN_HEADERS
    )

    assert response.status_code == 200
    course_id = response.json()["data"]["id"]

    yield course_id, lab_id

    await cleanup_course(course_id)
    await cleanup_resources(async_test_client, lab_id)
