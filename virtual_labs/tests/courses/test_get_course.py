"""Tests for course retrieval endpoints (GET /courses/{id} and GET /courses?vlab_name=...)."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.tests.courses.conftest import SERVICE_ADMIN_HEADERS
from virtual_labs.tests.utils import (
    get_headers,
    session_context_factory,
)

# ──────────────────────────────────────────────────────────────────────
# GET /courses/{course_id}
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_course_by_id_successfully(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.get(
        f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
    )

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

    response = await async_test_client.get(
        f"/courses/{course_id}", headers=SERVICE_ADMIN_HEADERS
    )

    data = response.json()["data"]
    assert isinstance(data["virtual_lab_name"], str)
    assert len(data["virtual_lab_name"]) > 0
    assert data["institution_name"] == "Open Brain Institute"


@pytest.mark.asyncio
async def test_get_course_by_id_not_found(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        f"/courses/{uuid4()}", headers=SERVICE_ADMIN_HEADERS
    )

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

    async with session_context_factory() as session:
        vlab = await session.scalar(
            select(VirtualLab).where(VirtualLab.id == UUID(vlab_id))
        )
        assert vlab is not None
        vlab_name = vlab.name

    # Search with a substring of the name
    search_term = vlab_name[:5]

    response = await async_test_client.get(
        "/courses", params={"vlab_name": search_term}, headers=SERVICE_ADMIN_HEADERS
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

    async with session_context_factory() as session:
        vlab = await session.scalar(
            select(VirtualLab).where(VirtualLab.id == UUID(vlab_id))
        )
        assert vlab is not None
        vlab_name = vlab.name

    response = await async_test_client.get(
        "/courses",
        params={"vlab_name": vlab_name.upper()},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) >= 1


@pytest.mark.asyncio
async def test_search_courses_no_results(
    async_test_client: AsyncClient,
) -> None:
    """Searching with a non-matching name should return empty list."""
    response = await async_test_client.get(
        "/courses",
        params={"vlab_name": "nonexistent-lab-xyz-99999"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_search_courses_requires_vlab_name_param(
    async_test_client: AsyncClient,
) -> None:
    """GET /courses without vlab_name query param should fail validation."""
    response = await async_test_client.get("/courses", headers=SERVICE_ADMIN_HEADERS)

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

    response = await async_test_client.get(
        "/courses", params={"vlab_name": "test"}, headers=headers
    )

    assert response.status_code == 403
