from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from virtual_labs.infrastructure.db.models import Notebook
from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "plan_id": 1,
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()

    lab_response = await client.post("/virtual-labs", json=body, headers=headers)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    project_body = {"name": f"Test Project {uuid4()}", "description": "Test"}
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    project_id = project_response.json()["data"]["project"]["id"]

    yield project_id
    await cleanup_resources(client=client, lab_id=lab_id)


@pytest_asyncio.fixture
async def mock_notebooks(async_test_session: AsyncSession, mock_project: UUID) -> None:
    current_time = datetime.now(timezone.utc)
    notebooks = [
        {
            "project_id": mock_project,
            "github_file_url": f"https://test_notebook_{i}",
            "created_at": current_time + timedelta(seconds=1),
        }
        for i in range(3)
    ]

    stmt = insert(Notebook).values(notebooks)
    await async_test_session.execute(stmt)
    await async_test_session.commit()
    return notebooks


@pytest.mark.asyncio
async def test_create_notebook(
    mock_project: UUID,
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.post(
        f"/projects/{mock_project}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "http://example_notebook"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_notebooks(
    mock_project: UUID, mock_notebooks: None, async_test_client: AsyncClient
) -> None:
    response = await async_test_client.get(
        f"/projects/{mock_project}/notebooks/",
        headers=get_headers(),
    )

    assert response.status_code == 200

    notebooks = response.json()["data"]["results"]

    urls = [n["github_file_url"] for n in notebooks]
    original_urls = [n["github_file_url"] for n in mock_notebooks]

    assert urls == original_urls
