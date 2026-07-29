from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_labs_shows_other_users_labs(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, _ = lab_with_project
    response = await async_test_client.get(
        "/admin/labs", params={"query": lab["name"]}, headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] >= 1
    listed = {item["id"] for item in body["data"]}
    assert lab["id"] in listed
    item = next(item for item in body["data"] if item["id"] == lab["id"])
    assert item["deleted"] is False
    assert item["owner_id"]
    assert item["projects_count"] == 1


@pytest.mark.asyncio
async def test_get_lab_detail_and_members(
    async_test_client: AsyncClient,
    maintainer_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, _ = lab_with_project

    detail = await async_test_client.get(
        f"/admin/labs/{lab['id']}", headers=maintainer_headers
    )
    assert detail.status_code == 200
    assert detail.json()["name"] == lab["name"]

    users = await async_test_client.get(
        f"/admin/labs/{lab['id']}/users", headers=maintainer_headers
    )
    assert users.status_code == 200
    assert users.json()["data"]["total"] >= 1

    invites = await async_test_client.get(
        f"/admin/labs/{lab['id']}/invites", headers=maintainer_headers
    )
    assert invites.status_code == 200
    assert isinstance(invites.json(), list)


@pytest.mark.asyncio
async def test_update_lab(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, _ = lab_with_project
    response = await async_test_client.patch(
        f"/admin/labs/{lab['id']}",
        json={"description": "updated by platform admin"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    updated = response.json()["data"]["virtual_lab"]
    assert updated["description"] == "updated by platform admin"


@pytest.mark.asyncio
async def test_soft_delete_lab_and_deleted_scope(
    async_test_client: AsyncClient,
    admin_headers: dict[str, str],
    lab_with_project: tuple[dict[str, Any], str],
) -> None:
    lab, _ = lab_with_project

    deleted = await async_test_client.delete(
        f"/admin/labs/{lab['id']}", headers=admin_headers
    )
    assert deleted.status_code == 200

    # detail still resolves for admins and carries the deletion state
    detail = await async_test_client.get(
        f"/admin/labs/{lab['id']}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["deleted"] is True

    # hidden from the default listing, present in the trash view
    default_list = await async_test_client.get(
        "/admin/labs", params={"query": lab["name"]}, headers=admin_headers
    )
    assert lab["id"] not in {item["id"] for item in default_list.json()["data"]}

    trash_list = await async_test_client.get(
        "/admin/labs",
        params={"query": lab["name"], "deleted_only": True},
        headers=admin_headers,
    )
    assert lab["id"] in {item["id"] for item in trash_list.json()["data"]}
