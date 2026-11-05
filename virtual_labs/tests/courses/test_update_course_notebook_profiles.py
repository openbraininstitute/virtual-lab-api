"""Tests for PATCH /courses/{course_id}/notebook-profiles."""

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers

ADMIN_HEADERS = get_headers()
NON_ADMIN_HEADERS = get_headers("test-1")


@pytest.mark.asyncio
async def test_set_notebook_profiles(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": ["small", "medium"]},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"]["allowed_notebook_profiles"] == ["small", "medium"]


@pytest.mark.asyncio
async def test_reset_notebook_profiles_to_all(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": ["small"]},
        headers=ADMIN_HEADERS,
    )

    response = await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": None},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"]["allowed_notebook_profiles"] is None


@pytest.mark.asyncio
async def test_reject_empty_notebook_profiles(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": []},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_duplicate_notebook_profiles(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": ["small", "small"]},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_notebook_profiles_forbidden_for_non_admin(
    async_test_client: AsyncClient,
    draft_course: tuple[str, str],
) -> None:
    course_id, _ = draft_course

    response = await async_test_client.patch(
        f"/courses/{course_id}/notebook-profiles",
        json={"allowed_notebook_profiles": ["small"]},
        headers=NON_ADMIN_HEADERS,
    )

    assert response.status_code == 403
