from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_projects_across_labs(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, project_id = lab_with_project
    response = await async_test_client.get(
        "/admin/projects",
        params={"virtual_lab_id": lab["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    item = body["data"][0]
    assert item["id"] == project_id
    assert item["virtual_lab_id"] == lab["id"]
    assert item["virtual_lab_name"] == lab["name"]


@pytest.mark.asyncio
async def test_get_project_detail(
    async_test_client: AsyncClient,
    maintainer_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    _, project_id = lab_with_project
    response = await async_test_client.get(
        f"/admin/projects/{project_id}", headers=maintainer_headers
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is False

    missing = await async_test_client.get(
        f"/admin/projects/{uuid4()}", headers=maintainer_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_soft_delete_and_restore_project(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    _, project_id = lab_with_project

    deleted = await async_test_client.delete(
        f"/admin/projects/{project_id}", headers=admin_headers
    )
    assert deleted.status_code == 200

    detail = await async_test_client.get(
        f"/admin/projects/{project_id}", headers=admin_headers
    )
    assert detail.json()["deleted"] is True

    restored = await async_test_client.post(
        f"/admin/projects/{project_id}/restore", headers=admin_headers
    )
    assert restored.status_code == 200
    assert restored.json()["deleted"] is False
    # restore must clear the soft-delete attribution too
    assert restored.json()["deleted_by"] is None

    # restoring a live project is rejected
    again = await async_test_client.post(
        f"/admin/projects/{project_id}/restore", headers=admin_headers
    )
    assert again.status_code == 400
