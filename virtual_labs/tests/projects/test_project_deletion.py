from uuid import uuid4

import pytest
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import get_headers


@pytest.mark.asyncio
async def test_vlm_project_deletion(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    response, headers = mock_lab_create
    virtual_lab_id = response.json()["data"]["virtual_lab"]["id"]

    payload = {
        "name": f"Test Project {uuid4()}",
        "description": "Test Project",
    }

    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json=payload,
        headers=headers,
    )
    project_id = response.json()["data"]["project"]["id"]

    headers = get_headers()
    response = await client.delete(
        f"/virtual-labs/{virtual_lab_id}/projects/{project_id}",
        headers=headers,
    )
    result = response.json()
    assert response.status_code == 200
    assert result["data"]["deleted"] is True
