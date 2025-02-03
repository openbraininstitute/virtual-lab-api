from datetime import datetime, timedelta
from typing import AsyncGenerator, TypedDict
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


class MockNotebook(TypedDict):
    project_id: UUID
    github_file_url: str
    created_at: datetime


@pytest_asyncio.fixture
async def mock_notebooks(
    async_test_session: AsyncSession, mock_project: UUID
) -> list[MockNotebook]:
    current_time = datetime(2000, 1, 1)
    notebooks = [
        MockNotebook(
            project_id=mock_project,
            github_file_url=f"https://test_notebook_{i}",
            created_at=current_time + timedelta(hours=i),
        )
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
    mock_project: UUID,
    mock_notebooks: list[MockNotebook],
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        f"/projects/{mock_project}/notebooks/",
        headers=get_headers(),
    )

    assert response.status_code == 200

    notebooks = response.json()["data"]["results"]

    urls = [n["github_file_url"] for n in notebooks]
    original_urls_desc = list(reversed([n["github_file_url"] for n in mock_notebooks]))

    assert urls == original_urls_desc


@pytest.mark.asyncio
async def test_paginated_notebooks(
    mock_project: UUID,
    mock_notebooks: list[MockNotebook],
    async_test_client: AsyncClient,
) -> None:
    page = 2
    page_size = 2

    response = await async_test_client.get(
        f"/projects/{mock_project}/notebooks/",
        headers=get_headers(),
        params={"page": page, "page_size": page_size},
    )

    assert response.status_code == 200

    notebooks = response.json()["data"]["results"]

    assert len(notebooks) == 1  # Only one record in last page

    paginated_urls = [n["github_file_url"] for n in notebooks]
    original_urls_desc = list(reversed([n["github_file_url"] for n in mock_notebooks]))
    expected_urls = original_urls_desc[(page - 1) * page_size : page * page_size]

    assert paginated_urls == expected_urls

    total_notebooks = len(mock_notebooks)

    assert response.json()["data"]["total"] == total_notebooks
