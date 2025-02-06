from datetime import datetime, timedelta
from typing import AsyncGenerator, TypedDict
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest import FixtureRequest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from virtual_labs.infrastructure.db.models import Notebook
from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_projects(
    request: FixtureRequest,
    async_test_client: AsyncClient,
) -> AsyncGenerator[list[str], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "plan_id": 1,
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()

    project_ids: list[str] = []

    lab_response = await client.post("/virtual-labs", json=body, headers=headers)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]

    for _ in range(getattr(request, "param", False) and request.param or 1):
        project_body = {"name": f"Test Project {uuid4()}", "description": "Test"}
        project_response = await client.post(
            f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
        )
        project_ids.append(project_response.json()["data"]["project"]["id"])

    yield project_ids
    await cleanup_resources(client=client, lab_id=lab_id)


class MockNotebook(TypedDict):
    project_id: str
    github_file_url: str
    created_at: datetime


@pytest_asyncio.fixture
async def mock_notebooks(
    request: FixtureRequest, async_test_session: AsyncSession, mock_projects: list[str]
) -> list[Notebook]:
    current_time = datetime(2000, 1, 1)

    n = getattr(request, "param", False) and request.param or 3

    notebooks = [
        MockNotebook(
            project_id=mock_projects[0],
            github_file_url=f"https://test_notebook_{i}",
            created_at=current_time + timedelta(hours=i),
        )
        for i in range(n)
    ]

    stmt = insert(Notebook).values(notebooks).returning(Notebook)
    res = await async_test_session.execute(stmt)
    inserted_notebooks = res.scalars().all()

    await async_test_session.commit()

    for n in inserted_notebooks:
        await async_test_session.refresh(n)

    return list(inserted_notebooks)


@pytest.mark.asyncio
async def test_create_notebook(
    mock_projects: list[str],
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.post(
        f"/projects/{mock_projects[0]}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "https://example_notebook"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_notebook_no_project(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.post(
        f"/projects/{str(uuid4())}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "https://example_notebook"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_projects", [2], indirect=True)
async def test_create_duplicate_notebook(
    mock_projects: list[str],
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.post(
        f"/projects/{mock_projects[0]}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "https://example_notebook"},
    )

    assert response.status_code == 200

    response = await async_test_client.post(
        f"/projects/{mock_projects[0]}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "https://example_notebook"},
    )

    assert response.status_code == 409

    response = await async_test_client.post(
        f"/projects/{mock_projects[1]}/notebooks/",
        headers=get_headers(),
        json={"github_file_url": "https://example_notebook"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_notebooks(
    mock_projects: list[str],
    mock_notebooks: list[Notebook],
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.get(
        f"/projects/{mock_projects[0]}/notebooks/",
        headers=get_headers(),
    )

    assert response.status_code == 200

    notebooks = response.json()["data"]["results"]

    urls = [n["github_file_url"] for n in notebooks]
    original_urls_desc = list(reversed([n.github_file_url for n in mock_notebooks]))

    assert urls == original_urls_desc


@pytest.mark.asyncio
async def test_paginated_notebooks(
    mock_projects: list[str],
    mock_notebooks: list[Notebook],
    async_test_client: AsyncClient,
) -> None:
    page = 2
    page_size = 2

    response = await async_test_client.get(
        f"/projects/{mock_projects[0]}/notebooks/",
        headers=get_headers(),
        params={"page": page, "page_size": page_size},
    )

    assert response.status_code == 200

    notebooks = response.json()["data"]["results"]

    assert len(notebooks) == 1  # Only one record in last page

    paginated_urls = [n["github_file_url"] for n in notebooks]
    original_urls_desc = list(reversed([n.github_file_url for n in mock_notebooks]))
    expected_urls = original_urls_desc[(page - 1) * page_size : page * page_size]

    assert paginated_urls == expected_urls

    total_notebooks = len(mock_notebooks)

    assert response.json()["data"]["total"] == total_notebooks


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_notebooks", [1], indirect=True)
async def test_delete_notebook(
    mock_notebooks: list[Notebook],
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.delete(
        f"/projects/{mock_notebooks[0].project_id}/notebooks/{mock_notebooks[0].id}",
        headers=get_headers(),
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_notebook_no_project(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.delete(
        f"/projects/{str(uuid4())}/notebooks/{str(uuid4())}",
        headers=get_headers(),
    )

    assert response.status_code == 404
