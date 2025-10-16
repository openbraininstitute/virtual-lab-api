from typing import Any, AsyncGenerator, Dict, Tuple
from uuid import UUID, uuid4

import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.domain.user import Workspace
from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.repositories.user_preference_repo import (
    UserPreferenceMutationRepository,
)
from virtual_labs.tests.utils import (
    cleanup_resources,
    get_headers,
    get_user_id_from_test_auth,
)


@pytest_asyncio.fixture
async def mock_user_with_lab_and_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[Tuple[Response, str, Dict[str, Any]], None]:
    """Create a mock user with a virtual lab and a project."""
    client = async_test_client
    headers = get_headers()

    # Clean up any existing virtual labs for this user BEFORE creating a new one
    existing_labs_response = await client.get(
        "/virtual-labs",
        headers=headers,
    )

    if existing_labs_response.status_code == 200:
        existing_labs = (
            existing_labs_response.json().get("data", {}).get("virtual_labs", [])
        )
        for lab in existing_labs:
            lab_id = lab.get("id")
            if lab_id:
                try:
                    await cleanup_resources(client, lab_id)
                except Exception as e:
                    print(f"Error cleaning up existing lab {lab_id}: {e}")

    # Create virtual lab
    vl_response = await client.post(
        "/virtual-labs",
        json={
            "name": f"Test Lab {uuid4()}",
            "description": "Test Lab for User Preferences",
            "reference_email": "user@test.org",
            "entity": "Test Entity",
            "email_status": "verified",
        },
        headers=headers,
    )
    assert vl_response.status_code == 200
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]

    project_response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/projects",
        json={
            "name": f"Test Project {uuid4()}",
            "description": "Test Project for User Preferences",
        },
        headers=headers,
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["project"]["id"]

    yield vl_response, virtual_lab_id, {"project_id": project_id, "headers": headers}

    await cleanup_resources(client, virtual_lab_id)


@pytest_asyncio.fixture
async def mock_user_with_multiple_projects(
    async_test_client: AsyncClient,
) -> AsyncGenerator[Tuple[str, Dict[str, str], Dict[str, str]], None]:
    """Create a mock user with a virtual lab and multiple projects."""
    client = async_test_client
    headers = get_headers()

    # Clean up any existing virtual labs for this user BEFORE creating a new one
    existing_labs_response = await client.get(
        "/virtual-labs",
        headers=headers,
    )

    if existing_labs_response.status_code == 200:
        existing_labs = (
            existing_labs_response.json().get("data", {}).get("virtual_labs", [])
        )
        for lab in existing_labs:
            lab_id = lab.get("id")
            if lab_id:
                try:
                    await cleanup_resources(client, lab_id)
                except Exception as e:
                    print(f"Error cleaning up existing lab {lab_id}: {e}")

    vl_response = await client.post(
        "/virtual-labs",
        json={
            "name": f"Test Lab {uuid4()}",
            "description": "Test Lab for Multiple Projects",
            "reference_email": "user@test.org",
            "entity": "Test Entity",
            "email_status": "verified",
        },
        headers=headers,
    )
    assert vl_response.status_code == 200
    virtual_lab_id = vl_response.json()["data"]["virtual_lab"]["id"]

    projects = {}
    for i in range(3):
        project_response = await client.post(
            f"/virtual-labs/{virtual_lab_id}/projects",
            json={
                "name": f"Test Project {i} {uuid4()}",
                "description": f"Test Project {i} description",
            },
            headers=headers,
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["project"]["id"]
        projects[f"project_{i}"] = project_id

    yield virtual_lab_id, projects, headers

    await cleanup_resources(client, virtual_lab_id)


@pytest_asyncio.fixture
async def mock_user_with_recent_workspace(
    mock_user_with_lab_and_project: Tuple[Response, str, Dict[str, Any]],
) -> AsyncGenerator[Tuple[str, str, Dict[str, Any]], None]:
    """Create a user with a virtual lab, project, and set a recent workspace preference."""
    vl_response, virtual_lab_id, data = mock_user_with_lab_and_project
    project_id = data["project_id"]
    headers = data["headers"]

    async with session_pool.session() as session:
        user_id = await get_user_id_from_test_auth(headers["Authorization"])

        preference_repo = UserPreferenceMutationRepository(session)
        workspace = Workspace(
            virtual_lab_id=UUID(virtual_lab_id), project_id=UUID(project_id)
        )
        await preference_repo.set_recent_workspace(user_id, workspace)

    yield virtual_lab_id, project_id, headers

    async with session_pool.session() as session:
        user_id = await get_user_id_from_test_auth(headers["Authorization"])
        preference_repo = UserPreferenceMutationRepository(session)
        await preference_repo.delete_user_preference(user_id)
        await session.commit()


@pytest_asyncio.fixture
async def mock_user_with_no_lab(
    async_test_client: AsyncClient,
) -> AsyncGenerator[Dict[str, str], None]:
    """Create a mock user with no virtual labs."""
    # Return headers for a user that exists but has no virtual labs
    headers = get_headers()
    yield headers
