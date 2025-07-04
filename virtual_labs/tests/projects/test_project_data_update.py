from http import HTTPStatus as status
from typing import Any

import pytest
from httpx import AsyncClient, Response


@pytest.mark.asyncio
async def test_vlm_update_project_data(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]

    new_name = "Test Project updated name"
    new_description = "Test Project updated description"

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"name": new_name, "description": new_description},
    )
    result = response.json()

    assert response.status_code == 200
    assert result["data"]["project"]["name"] == new_name
    assert result["data"]["project"]["description"] == new_description


@pytest.mark.asyncio
async def test_vlm_update_project_data_empty_should_fail(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]

    new_name = ""
    new_description = ""

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"name": new_name, "description": new_description},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_vlm_update_project_data_spaced_should_stripped(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]

    new_name = " new_spaced_name "
    new_description = " new_spaced_description "

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"name": new_name, "description": new_description},
    )
    result = response.json()

    assert response.status_code == 200

    assert result["data"]["project"]["name"] == new_name.strip()
    assert result["data"]["project"]["description"] == new_description.strip()


@pytest.mark.asyncio
async def test_vlm_update_project_name_only(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]

    new_name = "Test Project updated name"

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"name": new_name},
    )
    result = response.json()

    assert response.status_code == 200
    assert result["data"]["project"]["name"] == new_name


@pytest.mark.asyncio
async def test_vlm_update_project_name_with_existing_one(
    async_test_client: AsyncClient,
    mock_create_full_vl_projects: tuple[list[dict[str, Any]], dict[str, str]],
) -> None:
    client = async_test_client
    vl_projects, headers = mock_create_full_vl_projects
    project_id = vl_projects[0]["id"]
    virtual_lab_id = vl_projects[0]["virtual_lab_id"]

    new_name = vl_projects[1]["name"]

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"name": new_name},
    )

    assert response.status_code == status.BAD_REQUEST


@pytest.mark.asyncio
async def test_vlm_update_project_description_only(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    project_id = response.json()["data"]["project"]["id"]
    project_name = response.json()["data"]["project"]["name"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]

    new_description = "Test Project updated description"

    response = await client.patch(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
        json={"description": new_description},
    )
    result = response.json()

    assert response.status_code == 200
    assert result["data"]["project"]["name"] == project_name
    assert result["data"]["project"]["description"] == new_description
