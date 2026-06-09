"""Shared fixtures for seat tests.

Creates a course-enabled virtual lab (is_course=True) through the API,
which uses COURSE_LAB_POLICY (no billing/subscription required).
"""

from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, update

from virtual_labs.infrastructure.db.models import Seat, VirtualLab
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.utils import (
    cleanup_course,
    cleanup_resources,
    get_headers,
    get_or_create_institution,
    session_context_factory,
)

SERVICE_ADMIN_HEADERS = get_headers("test-service-admin")

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def cleanup_seats(course_id: str) -> None:
    async with session_context_factory() as session:
        await session.execute(delete(Seat).where(Seat.course_id == UUID(course_id)))
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await get_or_create_institution()


@pytest_asyncio.fixture
async def course_for_seats(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Create a course-enabled virtual lab and a course. Returns the course_id.

    Uses is_course=True so COURSE_LAB_POLICY is applied (no billing/subscription).
    """
    client = async_test_client
    headers = get_headers()

    # 1. Create a course-enabled vlab (no subscription needed)
    lab_body = {
        "name": f"Course Lab {uuid4()}",
        "description": "Test course lab",
        "reference_email": "course@test.org",
        "entity": "EPFL, Switzerland",
        "is_course": True,
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    lab_id = lab_response.json()["id"]

    # Mark as course lab (owner_id must be the service user for course validation)
    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    # 2. Create a project (needed as template_project_id)
    project_body = {
        "name": f"Template Project {uuid4()}",
        "description": "Template",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    # 3. Create a course for this vlab
    course_body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }
    course_response = await client.post(
        "/courses", json=course_body, headers=SERVICE_ADMIN_HEADERS
    )

    assert course_response.status_code == 200
    course_id = course_response.json()["data"]["id"]

    # 4. Set required dates and activate the course
    await client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": "2026-09-01T00:00:00Z",
            "end_date": "2026-12-15T00:00:00Z",
            "last_drop_date": "2026-09-14T00:00:00Z",
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    activate_response = await client.post(
        f"/courses/{course_id}/activate", headers=SERVICE_ADMIN_HEADERS
    )
    assert activate_response.status_code == 200

    yield course_id

    await cleanup_seats(course_id)
    await cleanup_course(course_id)
    await cleanup_resources(client, lab_id)


@pytest_asyncio.fixture
async def draft_course_for_seats(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Create a course-enabled virtual lab and a DRAFT course. Returns the course_id."""
    client = async_test_client
    headers = get_headers()

    lab_body = {
        "name": f"Course Lab {uuid4()}",
        "description": "Test course lab",
        "reference_email": "course@test.org",
        "entity": "EPFL, Switzerland",
        "is_course": True,
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    lab_id = lab_response.json()["id"]

    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    project_body = {
        "name": f"Template Project {uuid4()}",
        "description": "Template",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    course_body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }
    course_response = await client.post(
        "/courses", json=course_body, headers=SERVICE_ADMIN_HEADERS
    )

    assert course_response.status_code == 200
    course_id = course_response.json()["data"]["id"]

    yield course_id

    await cleanup_seats(course_id)
    await cleanup_course(course_id)
    await cleanup_resources(client, lab_id)


@pytest_asyncio.fixture
async def voided_course_for_seats(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Create a course-enabled virtual lab and a VOIDED course. Returns the course_id."""
    client = async_test_client
    headers = get_headers()

    lab_body = {
        "name": f"Course Lab {uuid4()}",
        "description": "Test course lab",
        "reference_email": "course@test.org",
        "entity": "EPFL, Switzerland",
        "is_course": True,
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    lab_id = lab_response.json()["id"]

    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    project_body = {
        "name": f"Template Project {uuid4()}",
        "description": "Template",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    course_body = {
        "virtual_lab_id": lab_id,
        "template_project_id": project_id,
        "institution_id": institution_id,
    }
    course_response = await client.post(
        "/courses", json=course_body, headers=SERVICE_ADMIN_HEADERS
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["data"]["id"]

    # Void the course
    void_response = await client.post(
        f"/courses/{course_id}/void", headers=SERVICE_ADMIN_HEADERS
    )
    assert void_response.status_code == 200

    yield course_id

    await cleanup_seats(course_id)
    await cleanup_course(course_id)
    await cleanup_resources(client, lab_id)
