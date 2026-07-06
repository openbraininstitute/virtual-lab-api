"""Tests for missing-student-emails endpoint — now queries CourseEnrolment."""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, update

from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.db.models import (
    Course,
    CourseEnrolment,
    VirtualLab,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.utils import (
    cleanup_resources,
    get_headers,
    get_or_create_institution,
)

SERVICE_ADMIN_HEADERS = get_headers("test-service-admin")


@pytest_asyncio.fixture
async def lab_with_enrolment(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, dict[str, str]]]:
    """Create a course-enabled vlab with an enrolment via API + DB insert."""
    client = async_test_client
    headers = get_headers()

    # 1. Create course-enabled vlab
    lab_response = await client.post(
        "/virtual-labs",
        json={
            "name": f"Course Lab {uuid4()}",
            "description": "Test",
            "reference_email": "user@test.org",
            "entity": "EPFL, Switzerland",
            "is_course": True,
        },
        headers=headers,
    )
    assert lab_response.status_code == 200, lab_response.json()
    lab_id = lab_response.json()["id"]

    # Allow multiple vlabs for this user
    async with session_pool.session() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    # 2. Create template project
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects",
        json={"name": f"Template {uuid4()}", "description": "Template"},
        headers=headers,
    )
    assert project_response.status_code == 200, project_response.json()
    project_id = project_response.json()["id"]

    # 3. Create course via API
    institution_id = await get_or_create_institution()
    course_response = await client.post(
        "/courses",
        json={
            "virtual_lab_id": lab_id,
            "template_project_id": project_id,
            "institution_id": institution_id,
        },
        headers=SERVICE_ADMIN_HEADERS,
    )
    assert course_response.status_code == 200, course_response.json()
    course_id = course_response.json()["data"]["id"]

    # 4. Insert enrolment directly (project_id is required)
    async with session_pool.session() as session:
        enrolment = CourseEnrolment(
            course_id=UUID(course_id),
            contact_email="existing@test.org",
            student_id="student-001",
            project_id=UUID(project_id),
        )
        session.add(enrolment)
        await session.commit()

    yield lab_id, headers

    # Cleanup
    async with session_pool.session() as session:
        await session.execute(
            delete(CourseEnrolment).where(CourseEnrolment.course_id == UUID(course_id))
        )
        await session.execute(delete(Course).where(Course.id == UUID(course_id)))
        await session.commit()

    await cleanup_resources(client=client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_missing_emails_returns_unassigned(
    async_test_client: AsyncClient,
    lab_with_enrolment: tuple[str, dict[str, str]],
) -> None:
    lab_id, headers = lab_with_enrolment
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["existing@test.org", "missing@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert sorted(response.json()) == ["missing@test.org"]


@pytest.mark.asyncio
async def test_missing_emails_all_exist(
    async_test_client: AsyncClient,
    lab_with_enrolment: tuple[str, dict[str, str]],
) -> None:
    lab_id, headers = lab_with_enrolment
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["existing@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_missing_emails_none_exist(
    async_test_client: AsyncClient,
    lab_with_enrolment: tuple[str, dict[str, str]],
) -> None:
    lab_id, headers = lab_with_enrolment
    response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/missing-student-emails",
        json={"emails": ["a@test.org", "b@test.org"]},
        headers=headers,
    )
    assert response.status_code == 200
    assert sorted(response.json()) == ["a@test.org", "b@test.org"]
