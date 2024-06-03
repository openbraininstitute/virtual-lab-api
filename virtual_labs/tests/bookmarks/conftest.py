from typing import AsyncGenerator
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient, Response


@pytest_asyncio.fixture
async def mock_create_project(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[str, str, dict[str, str], AsyncClient], None]:
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

    project = response.json()["data"]["project"]
    assert project["name"] == payload["name"]
    yield virtual_lab_id, project["id"], headers, client
