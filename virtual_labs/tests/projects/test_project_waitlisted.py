from typing import AsyncGenerator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import select, update

from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.infrastructure.kc.config import KeycloakRealm
from virtual_labs.tests.utils import (
    get_headers,
    get_user_id_from_test_auth,
    session_context_factory,
)


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

    vlab_member_group_id: str
    async with session_context_factory() as session:
        await session.execute(
            update(Project)
            .where(Project.id == UUID(project_id))
            .values(waitlisted_group_id=group_id)
        )
        result = await session.execute(
            select(VirtualLab.member_group_id).where(VirtualLab.id == UUID(virtual_lab_id))
        )
        vlab_member_group_id = str(result.scalar_one())
        await session.commit()

    waitlisted_headers = get_headers("test-1")
    user_id = str(await get_user_id_from_test_auth(waitlisted_headers["Authorization"]))
    KeycloakRealm.group_user_add(user_id=user_id, group_id=group_id)
    KeycloakRealm.group_user_add(user_id=user_id, group_id=vlab_member_group_id)

    yield project_id, virtual_lab_id, waitlisted_headers

    KeycloakRealm.group_user_remove(user_id=user_id, group_id=group_id)
    KeycloakRealm.group_user_remove(user_id=user_id, group_id=vlab_member_group_id)


@pytest.mark.asyncio
async def test_waitlisted_user_sees_project_in_vlab_list(
    async_test_client: AsyncClient,
    mock_waitlisted_project: tuple[str, str, dict[str, str]],
) -> None:
    project_id, virtual_lab_id, headers = mock_waitlisted_project

    list_response = await async_test_client.get(
        f"/virtual-labs/{virtual_lab_id}/projects", headers=headers
    )
    assert list_response.status_code == 200
    projects = list_response.json()["data"]

    assert any(p["id"] == project_id for p in projects)


@pytest.mark.asyncio
async def test_waitlisted_user_sees_project_in_list(
    async_test_client: AsyncClient,
    mock_waitlisted_project: tuple[str, str, dict[str, str]],
) -> None:
    project_id, _, headers = mock_waitlisted_project

    list_response = await async_test_client.get(
        "/virtual-labs/projects", headers=headers
    )
    assert list_response.status_code == 200
    projects = list_response.json()["data"]["results"]

    assert any(p["id"] == project_id for p in projects)
