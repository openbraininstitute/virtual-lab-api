"""Tests for course retrieval endpoints (GET /courses/{id} and GET /courses?vlab_name=...)."""

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
# GET /courses/{course_id}
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_course_by_id_successfully(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(f"/courses/{course_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == course_id
    assert data["status"] == "draft"
    assert "virtual_lab_name" in data
    assert "institution_name" in data


@pytest.mark.asyncio
async def test_get_course_by_id_includes_names(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Response should include resolved virtual_lab_name and institution_name."""
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(f"/courses/{course_id}", headers=headers)

    data = response.json()["data"]
    assert isinstance(data["virtual_lab_name"], str)
    assert len(data["virtual_lab_name"]) > 0
    assert data["institution_name"] == "Open Brain Institute"


@pytest.mark.asyncio
async def test_get_course_by_id_not_found(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(f"/courses/{uuid4()}", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_course_by_id_fails_without_auth(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.get(
        f"/courses/{course_id}",
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_course_by_id_fails_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.get(f"/courses/{course_id}", headers=headers)

    assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# GET /courses?vlab_name=...
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_courses_by_vlab_name(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Searching by partial vlab name should return the course."""
    course_id, vlab_id = draft_course
    headers = get_headers()

    # Get the vlab name so we can search for a substring
    from sqlalchemy import select as sa_select

    from virtual_labs.infrastructure.db.models import VirtualLab

    async with session_context_factory() as session:
        from uuid import UUID

        vlab = await session.scalar(
            sa_select(VirtualLab).where(VirtualLab.id == UUID(vlab_id))
        )
        assert vlab is not None
        vlab_name = vlab.name

    # Search with a substring of the name
    search_term = vlab_name[:5]

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/courses", params={"vlab_name": search_term}, headers=headers
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) >= 1
    course_ids = [c["id"] for c in data]
    assert course_id in course_ids


@pytest.mark.asyncio
async def test_search_courses_by_vlab_name_case_insensitive(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    """Search should be case-insensitive."""
    _, vlab_id = draft_course
    headers = get_headers()

    from sqlalchemy import select as sa_select

    from virtual_labs.infrastructure.db.models import VirtualLab

    async with session_context_factory() as session:
        from uuid import UUID

        vlab = await session.scalar(
            sa_select(VirtualLab).where(VirtualLab.id == UUID(vlab_id))
        )
        assert vlab is not None
        vlab_name = vlab.name

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/courses", params={"vlab_name": vlab_name.upper()}, headers=headers
        )

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1


@pytest.mark.asyncio
async def test_search_courses_no_results(
    async_test_client: AsyncClient,
) -> None:
    """Searching with a non-matching name should return empty list."""
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get(
            "/courses",
            params={"vlab_name": "nonexistent-lab-xyz-99999"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_search_courses_requires_vlab_name_param(
    async_test_client: AsyncClient,
) -> None:
    """GET /courses without vlab_name query param should fail validation."""
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.get("/courses", headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_courses_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        "/courses",
        params={"vlab_name": "test"},
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_courses_fails_for_non_admin(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.get(
            "/courses", params={"vlab_name": "test"}, headers=headers
        )

    assert response.status_code == 403
