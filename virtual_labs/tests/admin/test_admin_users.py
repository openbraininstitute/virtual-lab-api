from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.admin.conftest import LAB_OWNER
from virtual_labs.tests.utils import auth, get_user_id_from_test_auth


@pytest.mark.asyncio
async def test_search_users(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        "/admin/users", params={"query": LAB_OWNER}, headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 1
    assert any(item["username"] == LAB_OWNER for item in body["data"])


@pytest.mark.asyncio
async def test_get_user_overview_includes_lab_membership(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, project_id = lab_with_project
    owner_id = await get_user_id_from_test_auth(f"Bearer {auth(LAB_OWNER)}")

    response = await async_test_client.get(
        f"/admin/users/{owner_id}", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == LAB_OWNER

    lab_memberships = {item["id"]: item for item in body["virtual_labs"]}
    assert lab["id"] in lab_memberships
    assert lab_memberships[lab["id"]]["name"] == lab["name"]
    assert lab_memberships[lab["id"]]["role"] == "admin"

    project_memberships = {item["id"] for item in body["projects"]}
    assert project_id in project_memberships


@pytest.mark.asyncio
async def test_get_unknown_user_is_404(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        f"/admin/users/{uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404
