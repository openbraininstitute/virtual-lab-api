from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.repositories.group_repo import GroupQueryRepository


@pytest.mark.asyncio
async def test_vlm_project_creation(
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    (response, headers, _) = mock_create_project

    assert response.status_code == 200
    project_id = response.json()["id"]
    virtual_lab_id = response.json()["virtual_lab_id"]
    admin_group_name = f"proj/{virtual_lab_id}/{project_id}/admin"
    member_group_name = f"proj/{virtual_lab_id}/{project_id}/member"

    group_repo = GroupQueryRepository()

    admin_group = group_repo.retrieve_group_by_name(name=admin_group_name)
    member_group = group_repo.retrieve_group_by_name(name=member_group_name)

    # Test Kc group creation
    assert admin_group is not None
    assert member_group is not None


@pytest.mark.parametrize(
    "mock_create_project",
    [{"name": " spaced name ", "description": " spaced description "}],
    indirect=True,
)
@pytest.mark.asyncio
async def test_vlm_project_creation_trim_name_description(
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    (response, headers, payload) = mock_create_project

    assert response.status_code == 200

    project_name = response.json()["name"]
    project_description = response.json()["description"]

    assert project_name == payload["name"].strip()
    assert project_description == payload["description"].strip()


@pytest.mark.asyncio
async def test_vlm_project_creation_default_response_is_project(
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    response, _, _ = mock_create_project

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "virtual_lab_id" in data
    assert "project" not in data
    assert "balance_added" not in data
    assert "virtual_lab" not in data


@pytest.mark.asyncio
async def test_vlm_project_creation_expands_balance_and_virtual_lab(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["id"]

    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        params=[("expand", "balance"), ("expand", "virtual_lab")],
        json={
            "name": f"Expanded Project {uuid4()}",
            "description": "Test Project",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["virtual_lab_id"] == virtual_lab_id
    assert data["balance_added"] in {True, False}
    assert data["virtual_lab"]["id"] == virtual_lab_id


@pytest.mark.asyncio
async def test_vlm_project_creation_invalid_expand_is_validation_error(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["id"]

    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        params={"expand": "unknown"},
        json={
            "name": f"Invalid Expand Project {uuid4()}",
            "description": "Test Project",
        },
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_vlm_project_list_direct_paginated_response(
    async_test_client: AsyncClient,
    mock_create_full_vl_projects: tuple[list[dict[str, str]], dict[str, str]],
) -> None:
    client = async_test_client
    projects, headers = mock_create_full_vl_projects
    virtual_lab_id = projects[0]["virtual_lab_id"]

    response = await client.get(
        f"/virtual-labs/{virtual_lab_id}/projects",
        params={
            "page": 1,
            "page_size": 2,
            "order_by": "name",
            "order_direction": "asc",
        },
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"data", "pagination"}
    assert len(data["data"]) <= 2
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["page_size"] == 2
    assert data["pagination"]["total_items"] >= len(data["data"])


@pytest.mark.asyncio
async def test_vlm_project_list_invalid_order_by_is_validation_error(
    async_test_client: AsyncClient,
    mock_create_full_vl_projects: tuple[list[dict[str, str]], dict[str, str]],
) -> None:
    client = async_test_client
    projects, headers = mock_create_full_vl_projects
    virtual_lab_id = projects[0]["virtual_lab_id"]

    response = await client.get(
        f"/virtual-labs/{virtual_lab_id}/projects",
        params={"order_by": "invalid"},
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_projects_per_vlab_with_same_name_should_failed(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["id"]

    common_name = "Test Project Same Name"

    project_1 = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json={
            "name": common_name,
            "description": "Test Project",
        },
    )

    assert project_1.status_code == 200
    project_2 = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json={
            "name": common_name,
            "description": "Test Project",
        },
    )
    assert project_2.status_code == 400


@pytest_asyncio.fixture
async def mock_create_project_with_users(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[Response, None]:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["id"]

    payload = {
        "name": f"Test Project {uuid4()}",
        "description": "Test Project",
    }
    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json=payload,
    )
    yield response
