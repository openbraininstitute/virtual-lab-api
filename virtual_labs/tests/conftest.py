import asyncio
from typing import Any, AsyncGenerator, cast
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import delete

from virtual_labs.api import app
from virtual_labs.infrastructure.db.config import session_context_factory
from virtual_labs.infrastructure.db.models import Project
from virtual_labs.tests.utils import get_headers

VL_COUNT = 2
PROJECTS_PER_VL_COUNT = 2


@pytest_asyncio.fixture()
async def async_test_client() -> AsyncGenerator[AsyncClient, None]:
    headers = get_headers()
    async with AsyncClient(
        app=app,
        base_url="http://localhost:8000",
        headers=headers,
    ) as ac:
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

    yield response, headers


@pytest_asyncio.fixture
async def mock_create_projects(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[UUID, float, list[UUID], dict[str, str]], None]:
    client = async_test_client
    vl_response, headers = mock_lab_create
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]
    virtual_lab_budget = vl_response.json()["data"]["virtual_lab"]["budget"]

    projects: list[UUID] = []

    for i in range(3):
        payload = {
            "name": f"Test Project {i} {uuid4()}",
            "description": f"Test Project description {i}",
        }

        response = await client.post(
            f"/virtual-labs/{virtual_lab_id}/projects",
            json=payload,
        )
        project_id = response.json()["data"]["project"]["id"]

        response = await client.patch(
            f"/virtual-labs/{virtual_lab_id}/projects/{project_id}/budget",
            json={"new_budget": float(virtual_lab_budget) / 3},
        )

        projects.append(project_id)

    yield cast(UUID, virtual_lab_id), cast(float, virtual_lab_budget), projects, headers

    for id in projects:
        response = await client.delete(
            f"/virtual-labs/{virtual_lab_id}/projects/{id}",
        )


async def mock_create_virtual_lab(
    client: AsyncClient,
) -> str:
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

    return cast(str, response.json()["data"]["virtual_lab"]["id"])


@pytest_asyncio.fixture
async def mock_create_vl_projects(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[list[dict[str, list[UUID]]], dict[str, str]], None]:
    client = async_test_client
    headers = get_headers()

    vl_projects: list[dict[str, list[UUID]]] = []

    for i in range(VL_COUNT):
        virtual_lab_id = await mock_create_virtual_lab(async_test_client)

        projects: list[UUID] = []
        payload = {
            "name": f"existed project {i}",
            "description": f"existed project description {i}",
        }
        response = await client.post(
            f"/virtual-labs/{virtual_lab_id}/projects",
            json=payload,
        )
        project_id = response.json()["data"]["project"]["id"]
        projects.append(project_id)

        for j in range(PROJECTS_PER_VL_COUNT):
            payload = {
                "name": f"Test Project {j} {uuid4()}",
                "description": f"Test Project description {j}",
            }

            response = await client.post(
                f"/virtual-labs/{virtual_lab_id}/projects",
                json=payload,
            )
            project_id = response.json()["data"]["project"]["id"]
            projects.append(project_id)

        vl_projects.append({virtual_lab_id: projects})

    yield vl_projects, headers

    for elt in vl_projects:
        for vl_id, projects in elt.items():
            await client.delete(
                f"/virtual-labs/{vl_id}",
            )
            async with session_context_factory() as session:
                await session.execute(
                    statement=delete(Project).where(Project.id.in_(projects))
                )
                await session.commit()
