import pytest
from httpx import AsyncClient, Response
from requests import get

from virtual_labs.infrastructure.settings import settings


@pytest.mark.asyncio
async def test_vlm_update_project_data(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    response, headers = mock_create_project

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

    # Test Nexus project deprecation
    nexus_project = get(
        f"{settings.NEXUS_DELTA_URI}/projects/{virtual_lab_id}/{str(project_id)}",
        headers=headers,
    )

    result = nexus_project.json()
    assert result["description"] == new_description
