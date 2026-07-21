from typing import AsyncGenerator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import update

from virtual_labs.infrastructure.db.models import Project
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.tests.utils import (
    get_headers,
    get_user_id_from_test_auth,
    session_context_factory,
)


@pytest.mark.asyncio
async def test_list_projects_includes_waitlisted_field(
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
    async_test_client: AsyncClient,
) -> None:
    response, headers, _ = mock_create_project
    assert response.status_code == 200

    list_response = await async_test_client.get(
        "/virtual-labs/projects", headers=headers
    )
    assert list_response.status_code == 200
    projects = list_response.json()["data"]["results"]
    assert len(projects) >= 1
    assert all("waitlisted" in p for p in projects)


@pytest_asyncio.fixture
async def mock_waitlisted_project(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> AsyncGenerator[tuple[str, str, dict[str, str]], None]:
    """Creates a project as 'test', creates the waitlisted KC group, stores it
    on the project row, then adds 'test-1' (no other membership) to that group."""
    response, _, _ = mock_create_project
    assert response.status_code == 200

    project_id = response.json()["id"]
    virtual_lab_id = response.json()["virtual_lab_id"]
    group_name = f"proj/{virtual_lab_id}/{project_id}/waitlisted"

    group_id_or_none = KeycloakRealm.create_group({"name": group_name})
    assert group_id_or_none is not None
    group_id: str = group_id_or_none

    # Store the waitlisted_group_id on the project so the repo query picks it up
    async with session_context_factory() as session:
        await session.execute(
            update(Project)
            .where(Project.id == UUID(project_id))
            .values(waitlisted_group_id=group_id)
        )
        await session.commit()

    # test-1 has no admin/member membership — only waitlisted
    waitlisted_headers = get_headers("test-1")
    user_id = str(await get_user_id_from_test_auth(waitlisted_headers["Authorization"]))
    KeycloakRealm.group_user_add(user_id=user_id, group_id=group_id)

    yield project_id, virtual_lab_id, waitlisted_headers

    KeycloakRealm.group_user_remove(user_id=user_id, group_id=group_id)


@pytest.mark.asyncio
async def test_waitlisted_project_is_flagged_in_list(
    async_test_client: AsyncClient,
    mock_waitlisted_project: tuple[str, str, dict[str, str]],
) -> None:
    project_id, _, headers = mock_waitlisted_project

    list_response = await async_test_client.get(
        "/virtual-labs/projects", headers=headers
    )
    assert list_response.status_code == 200
    projects = list_response.json()["data"]["results"]

    target = next((p for p in projects if p["id"] == project_id), None)
    assert target is not None
    assert target["waitlisted"] is True


@pytest.mark.asyncio
async def test_non_waitlisted_project_has_waitlisted_false(
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
    async_test_client: AsyncClient,
) -> None:
    response, headers, _ = mock_create_project
    assert response.status_code == 200
    project_id = response.json()["id"]

    list_response = await async_test_client.get(
        "/virtual-labs/projects", headers=headers
    )
    assert list_response.status_code == 200
    projects = list_response.json()["data"]["results"]

    target = next((p for p in projects if p["id"] == project_id), None)
    assert target is not None
    assert target["waitlisted"] is False
