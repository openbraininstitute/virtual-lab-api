from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete, select

from virtual_labs.infrastructure.db.models import Course, Project, VirtualLab
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import get_headers, session_context_factory


def _mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def _mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def _get_or_create_institution() -> str:
    """Get the OBI institution ID, creating it if needed."""
    from virtual_labs.infrastructure.db.models import Institution

    async with session_context_factory() as session:
        result = await session.scalar(
            select(Institution.id).where(Institution.name == "Open Brain Institute")
        )
        if result:
            return str(result)

        # Create OBI institution for test
        institution = Institution(
            name="Open Brain Institute",
            contact_email="obi-virtual-lab@openbraininstitute.org",
        )
        session.add(institution)
        await session.commit()
        await session.refresh(institution)
        return str(institution.id)


def _make_course_payload(institution_id: str) -> dict:
    return {
        "name": f"Test Course {uuid4()}",
        "description": "A test course",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
        "template_project_id": str(uuid4()),  # placeholder, will be created by use case
    }


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await _get_or_create_institution()


@pytest_asyncio.fixture
async def mock_create_course(
    async_test_client: AsyncClient,
    institution_id: str,
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    headers = get_headers()

    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course for integration",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    yield response, headers

    # Cleanup: delete course, project, and vlab created during the test
    if response.status_code == 200:
        data = response.json().get("data", {})
        vlab_id = data.get("virtual_lab_id")
        if vlab_id:
            await _cleanup_course_resources(vlab_id)


async def _cleanup_course_resources(vlab_id: str) -> None:
    """Clean up all resources created during a course creation test."""
    from uuid import UUID

    from virtual_labs.repositories.group_repo import GroupMutationRepository

    async with session_context_factory() as session:
        # Delete course
        await session.execute(
            delete(Course).where(Course.virtual_lab_id == UUID(vlab_id))
        )

        # Get project group IDs before deleting
        projects = (
            await session.execute(
                select(Project.admin_group_id, Project.member_group_id).where(
                    Project.virtual_lab_id == UUID(vlab_id)
                )
            )
        ).all()

        # Delete projects
        await session.execute(
            delete(Project).where(Project.virtual_lab_id == UUID(vlab_id))
        )

        # Get vlab group IDs before deleting
        vlab = (
            await session.execute(
                select(VirtualLab.admin_group_id, VirtualLab.member_group_id).where(
                    VirtualLab.id == UUID(vlab_id)
                )
            )
        ).first()

        # Delete vlab
        await session.execute(delete(VirtualLab).where(VirtualLab.id == UUID(vlab_id)))
        await session.commit()

    # Delete KC groups
    group_repo = GroupMutationRepository()
    for project in projects:
        group_repo.delete_group(group_id=project[0])
        group_repo.delete_group(group_id=project[1])
    if vlab:
        group_repo.delete_group(group_id=vlab[0])
        group_repo.delete_group(group_id=vlab[1])


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_course_created_successfully(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    assert "id" in data
    assert "virtual_lab_id" in data
    assert "institution_id" in data
    assert "template_project_id" in data
    assert data["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_course_creates_keycloak_groups(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    vlab_id = data["virtual_lab_id"]

    group_repo = GroupQueryRepository()

    # Verify vlab KC groups were created
    admin_group = group_repo.retrieve_group_by_name(name=f"vlab/{vlab_id}/admin")
    member_group = group_repo.retrieve_group_by_name(name=f"vlab/{vlab_id}/member")
    assert admin_group is not None
    assert member_group is not None

    # Verify project KC groups were created
    project_id = data["template_project_id"]
    proj_admin_group = group_repo.retrieve_group_by_name(
        name=f"proj/{vlab_id}/{project_id}/admin"
    )
    proj_member_group = group_repo.retrieve_group_by_name(
        name=f"proj/{vlab_id}/{project_id}/member"
    )
    assert proj_admin_group is not None
    assert proj_member_group is not None


@pytest.mark.asyncio
async def test_course_creates_virtual_lab_and_project(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    vlab_id = data["virtual_lab_id"]
    project_id = data["template_project_id"]

    from uuid import UUID

    # Verify virtual lab exists in DB
    async with session_context_factory() as session:
        vlab = await session.scalar(
            select(VirtualLab).where(VirtualLab.id == UUID(vlab_id))
        )
        assert vlab is not None
        assert vlab.deleted is False

        # Verify project exists in DB
        project = await session.scalar(
            select(Project).where(Project.id == UUID(project_id))
        )
        assert project is not None
        assert project.virtual_lab_id == UUID(vlab_id)


@pytest.mark.asyncio
async def test_course_creation_fails_without_auth(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
    }

    response = await async_test_client.post(
        "/courses",
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_course_creation_fails_for_non_admin_user(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_course_creation_fails_without_name(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "description": "A test course",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_fails_without_entity(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course",
        "institution_id": institution_id,
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_fails_without_institution_id(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course",
        "entity": "EPFL, Switzerland",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_course_creation_with_optional_dates(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Course {uuid4()}",
        "description": "A test course with dates",
        "entity": "EPFL, Switzerland",
        "institution_id": institution_id,
        "start_date": "2026-09-01",
        "end_date": "2026-12-15",
        "last_drop_date": "2026-10-01",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.post(
            "/courses",
            json=body,
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["start_date"] == "2026-09-01"
    assert data["end_date"] == "2026-12-15"
    assert data["last_drop_date"] == "2026-10-01"

    # Cleanup
    vlab_id = data.get("virtual_lab_id")
    if vlab_id:
        await _cleanup_course_resources(vlab_id)


@pytest.mark.asyncio
async def test_course_default_status_is_draft(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
