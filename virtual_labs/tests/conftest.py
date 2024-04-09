import asyncio
from typing import Any, AsyncGenerator, cast
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.api import app
from virtual_labs.tests.utils import get_headers


@pytest_asyncio.fixture()
async def async_test_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://localhost:8000") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session", autouse=True)
def event_loop(request: Any) -> Any:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "budget": 10000,
        "plan_id": 1,
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    yield response, headers

    lab_id = response.json()["data"]["virtual_lab"]["id"]
    response = await client.delete(
        f"/virtual-labs/{lab_id}",
        headers=get_headers(),
    )
    assert response.status_code == 200


@pytest_asyncio.fixture
async def mock_create_project(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    vl_response, _ = mock_lab_create
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]

    payload = {
        "name": f"Test Project {uuid4()}",
        "description": "Test Project",
    }
    headers = get_headers()
    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json=payload,
        headers=headers,
    )
    print("respo", response)
    yield response, headers


@pytest_asyncio.fixture
async def mock_create_projects(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[UUID, float, list[UUID], dict[str, str]], None]:
    client = async_test_client
    vl_response, _ = mock_lab_create
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]
    virtual_lab_budget = vl_response.json()["data"]["virtual_lab"]["budget"]

    projects: list[UUID] = []

    for i in range(3):
        payload = {
            "name": f"Test Project {i} {uuid4()}",
            "description": f"Test Project description {i}",
        }
        headers = get_headers()
        response = await client.post(
            f"/virtual-labs/{virtual_lab_id}/projects",
            json=payload,
            headers=headers,
        )
        project_id = response.json()["data"]["project"]["id"]

        response = await client.patch(
            f"/virtual-labs/{virtual_lab_id}/projects/{project_id}/budget",
            json={"new_budget": float(virtual_lab_budget) / 3},
            headers=headers,
        )

        projects.append(project_id)

    yield cast(UUID, virtual_lab_id), cast(float, virtual_lab_budget), projects, headers

    for id in projects:
        response = await client.delete(
            f"/virtual-labs/{virtual_lab_id}/projects/{id}",
            headers=headers,
        )
