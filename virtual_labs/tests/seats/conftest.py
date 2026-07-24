"""Shared fixtures for seat tests.

Creates a course-enabled virtual lab (is_course=True) through the API,
which uses COURSE_LAB_POLICY (no billing/subscription required).
"""

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import and_, delete, select, update

from virtual_labs.infrastructure.db.models import (
    CourseEnrolment,
    Project,
    Seat,
    VirtualLab,
)
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
        # Clear seat FK to enrolment first
        await session.execute(
            update(Seat)
            .where(Seat.course_id == UUID(course_id))
            .values(enrolment_id=None)
        )
        # Materialize project IDs linked to enrolments before deleting them
        enrolment_project_rows = (
            (
                await session.execute(
                    select(CourseEnrolment.project_id).where(
                        and_(
                            CourseEnrolment.course_id == UUID(course_id),
                            CourseEnrolment.project_id.is_not(None),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        # Delete enrolments first (they hold the FK to project)
        await session.execute(
            delete(CourseEnrolment).where(CourseEnrolment.course_id == UUID(course_id))
        )
        # Now delete the projects that were linked to those enrolments
        if enrolment_project_rows:
            await session.execute(
                delete(Project).where(Project.id.in_(enrolment_project_rows))
            )
        # Delete seats
        await session.execute(delete(Seat).where(Seat.course_id == UUID(course_id)))
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await get_or_create_institution()


async def _create_active_course(
    client: AsyncClient,
    institution_id: str,
    start_date: datetime | None = None,
) -> AsyncGenerator[str, None]:
    """Shared factory: create a course-enabled vlab + active course. Yields course_id."""
    headers = get_headers()
    now = start_date or datetime.now(timezone.utc)

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

    await client.patch(
        f"/courses/{course_id}",
        json={
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=180)).isoformat(),
            "last_drop_date": (now + timedelta(days=14)).isoformat(),
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
async def course_for_seats(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Active course with start_date=now (course already started)."""
    async for course_id in _create_active_course(async_test_client, institution_id):
        yield course_id


@pytest_asyncio.fixture
async def future_course_for_seats(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[str, None]:
    """Active course with start_date=now+1d (course not yet started)."""
    future_start = datetime.now(timezone.utc) + timedelta(days=1)
    async for course_id in _create_active_course(
        async_test_client, institution_id, start_date=future_start
    ):
        yield course_id


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
