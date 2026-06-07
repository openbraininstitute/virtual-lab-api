"""Tests for the create-course endpoint.

The endpoint assigns an existing virtual lab and project to a new course.
It does NOT provision KC groups, accounting, or create vlab/project records.
"""

from typing import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
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
    """Get the OBI institution ID, creating it if needed."""
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


@pytest_asyncio.fixture
async def institution_id() -> str:
    return await _get_or_create_institution()


@pytest_asyncio.fixture
async def vlab_with_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, str], None]:
    """Create a real virtual lab + project to be assigned to a course."""
    from uuid import UUID

    from sqlalchemy import update

    from virtual_labs.infrastructure.db.models import VirtualLab
    from virtual_labs.tests.utils import cleanup_resources

    lab_data, project_id = await create_mock_lab_with_project(async_test_client)
    lab_id = lab_data["id"]

    # Mark the lab as a course lab by setting owner_id to the course user
    async with session_context_factory() as session:
        await session.execute(
            update(VirtualLab)
            .where(VirtualLab.id == UUID(lab_id))
            .values(owner_id=settings.MULTIPLE_VLABS_ALLOWED_USER_ID)
        )
        await session.commit()

    yield lab_id, project_id

    await cleanup_resources(async_test_client, lab_id)


def _make_course_payload(
    virtual_lab_id: str, template_project_id: str, institution_id: str
) -> dict:
    return {
        "virtual_lab_id": virtual_lab_id,
        "template_project_id": template_project_id,
        "institution_id": institution_id,
    }


@pytest_asyncio.fixture
async def mock_create_course(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    headers = get_headers()
    vlab_id, project_id = vlab_with_project

    body = _make_course_payload(vlab_id, project_id, institution_id)

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

    # Cleanup: delete the course row only (vlab/project cleaned by vlab_with_project fixture)
    if response.status_code == 200:
        data = response.json().get("data", {})
        course_id = data.get("id")
        if course_id:
            await _cleanup_course(course_id)


async def _cleanup_course(course_id: str) -> None:
    """Delete the course row."""
    from uuid import UUID

    async with session_context_factory() as session:
        await session.execute(delete(Course).where(Course.id == UUID(course_id)))
        await session.commit()


# ──────────────────────────────────────────────────────────────────────
# Happy-path tests
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
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_course_assigns_existing_vlab_and_project(
    mock_create_course: tuple[Response, dict[str, str]],
    vlab_with_project: tuple[str, str],
) -> None:
    """The course should reference the pre-existing vlab and project, not create new ones."""
    response, _ = mock_create_course
    vlab_id, project_id = vlab_with_project

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["virtual_lab_id"] == vlab_id
    assert data["template_project_id"] == project_id


@pytest.mark.asyncio
async def test_course_default_status_is_draft(
    mock_create_course: tuple[Response, dict[str, str]],
) -> None:
    response, _ = mock_create_course

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_course_creation_with_optional_dates(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    headers = get_headers()
    vlab_id, project_id = vlab_with_project

    body = {
        "virtual_lab_id": vlab_id,
        "template_project_id": project_id,
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

    # Cleanup course
    course_id = data.get("id")
    if course_id:
        await _cleanup_course(course_id)


# ──────────────────────────────────────────────────────────────────────
# Validation / error tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_course_creation_fails_with_nonexistent_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "virtual_lab_id": str(uuid4()),
        "template_project_id": str(uuid4()),
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

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_course_creation_fails_with_nonexistent_project(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    headers = get_headers()
    vlab_id, _ = vlab_with_project

    body = {
        "virtual_lab_id": vlab_id,
        "template_project_id": str(uuid4()),  # non-existent project
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

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_course_creation_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    body = {
        "virtual_lab_id": str(uuid4()),
        "template_project_id": str(uuid4()),
        "institution_id": str(uuid4()),
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
) -> None:
    headers = get_headers()
    body = {
        "virtual_lab_id": str(uuid4()),
        "template_project_id": str(uuid4()),
        "institution_id": str(uuid4()),
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
async def test_course_creation_fails_without_virtual_lab_id(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "template_project_id": str(uuid4()),
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
async def test_course_creation_fails_without_template_project_id(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    headers = get_headers()
    body = {
        "virtual_lab_id": str(uuid4()),
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
        "virtual_lab_id": str(uuid4()),
        "template_project_id": str(uuid4()),
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
async def test_course_creation_fails_duplicate_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
    vlab_with_project: tuple[str, str],
) -> None:
    """A virtual lab can only have one course (unique constraint)."""
    headers = get_headers()
    vlab_id, project_id = vlab_with_project
    body = _make_course_payload(vlab_id, project_id, institution_id)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo

        # First creation should succeed
        resp1 = await async_test_client.post("/courses", json=body, headers=headers)
        assert resp1.status_code == 200

        # Second creation with same vlab should fail (unique constraint)
        resp2 = await async_test_client.post("/courses", json=body, headers=headers)
        assert resp2.status_code == 409

    # Cleanup
    course_id = resp1.json()["data"].get("id")
    if course_id:
        await _cleanup_course(course_id)


@pytest.mark.asyncio
async def test_course_creation_fails_for_regular_vlab(
    async_test_client: AsyncClient,
    institution_id: str,
) -> None:
    """A course cannot be created on a regular (non-course) virtual lab."""
    from virtual_labs.tests.utils import cleanup_resources

    # Create a normal lab (owner is the regular test user, not the course user)
    lab_data, project_id = await create_mock_lab_with_project(async_test_client)
    lab_id = lab_data["id"]

    headers = get_headers()
    body = _make_course_payload(lab_id, project_id, institution_id)

    try:
        with patch(
            "virtual_labs.core.authorization.verify_service_admin.kc_auth"
        ) as mock_kc:
            mock_kc.userinfo.side_effect = _mock_admin_userinfo
            response = await async_test_client.post(
                "/courses",
                json=body,
                headers=headers,
            )

        assert response.status_code == 403
    finally:
        await cleanup_resources(async_test_client, lab_id)
