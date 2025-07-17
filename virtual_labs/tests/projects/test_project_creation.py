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
    project_id = response.json()["data"]["project"]["id"]
    virtual_lab_id = response.json()["data"]["virtual_lab_id"]
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

    project_name = response.json()["data"]["project"]["name"]
    project_description = response.json()["data"]["project"]["description"]

    assert project_name == payload["name"].strip()
    assert project_description == payload["description"].strip()


@pytest.mark.asyncio
async def test_create_projects_per_vlab_with_same_name_should_failed(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]

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
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]

    payload = {
        "name": f"Test Project {uuid4()}",
        "description": "Test Project",
    }
    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json=payload,
    )
    yield response


@pytest.mark.asyncio
async def test_vlm_project_with_members_creation(
    mock_create_project_with_users: Response,
) -> None:
    response = mock_create_project_with_users

    assert response.status_code == 200
    failed_invites = response.json()["data"]["failed_invites"]
    assert failed_invites == []
