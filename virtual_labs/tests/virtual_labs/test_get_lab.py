import copy
from http import HTTPStatus
from typing import Any, AsyncGenerator, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.infrastructure.db.models import Course
from virtual_labs.tests.utils import (
    cleanup_resources,
    get_headers,
    session_context_factory,
)


@pytest_asyncio.fixture
async def mock_lab_without_course(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, dict[str, Any], dict[str, str]], None]:
    """Creates a standard virtual lab."""
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()
    lab_create_response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    assert lab_create_response.status_code == 200
    lab = lab_create_response.json()

    yield client, lab, headers
    await cleanup_resources(client=client, lab_id=lab["id"])


@pytest_asyncio.fixture
async def mock_lab_with_course(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, dict[str, Any], dict[str, str], str], None]:
    """Creates a virtual lab with a project and a course linked to it."""
    client = async_test_client
    headers = get_headers()

    # Create lab
    lab_body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    lab_response = await client.post("/virtual-labs", json=lab_body, headers=headers)
    assert lab_response.status_code == 200
    lab = lab_response.json()
    lab_id = lab["id"]

    # Create project (needed as template_project_id)
    project_body = {"name": f"Template Project {uuid4()}", "description": "Template"}
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects", json=project_body, headers=headers
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    # Create course record in DB
    async with session_context_factory() as session:
        course = Course(
            virtual_lab_id=UUID(lab_id),
            template_project_id=UUID(project_id),
        )
        session.add(course)
        await session.commit()

    yield client, lab, headers, project_id
    await cleanup_resources(client=client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_get_lab_by_id_without_course(
    mock_lab_without_course: tuple[AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_without_course
    lab_id = lab["id"]

    response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert response.status_code == HTTPStatus.OK

    actual = response.json()
    assert actual["id"] == lab_id
    assert actual["name"] == lab["name"]
    assert actual["description"] == lab["description"]
    assert actual["reference_email"] == lab["reference_email"]
    assert actual["entity"] == lab["entity"]
    assert actual["created_at"] == lab["created_at"]
    assert actual["course"] is None
    assert "admins" not in actual
    assert "owner" not in actual


@pytest.mark.asyncio
async def test_get_lab_by_id_expands_admins_and_owner(
    mock_lab_without_course: tuple[AsyncClient, dict[str, str], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_without_course
    lab_id = lab["id"]

    response = await client.get(
        f"/virtual-labs/{lab_id}",
        params=[("expand", "admins"), ("expand", "owner")],
        headers=headers,
    )
    assert response.status_code == HTTPStatus.OK

    actual = response.json()
    assert actual["id"] == lab_id
    assert actual["admins"]
    assert actual["owner"]["id"] is not None


@pytest.mark.asyncio
async def test_get_lab_by_id_with_course(
    mock_lab_with_course: tuple[AsyncClient, dict[str, Any], dict[str, str], str],
) -> None:
    client, lab, headers, project_id = mock_lab_with_course
    lab_id = lab["id"]

    response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert response.status_code == HTTPStatus.OK

    actual = response.json()
    assert actual["id"] == lab_id
    assert actual["course"] is not None
    assert actual["course"]["virtual_lab_id"] == lab_id
    assert actual["course"]["template_project_id"] == project_id
    assert actual["course"]["institution_id"] is None
    assert actual["course"]["start_date"] is None
    assert actual["course"]["end_date"] is None
    assert actual["course"]["last_drop_date"] is None


def assert_get_and_delete_body_are_same(
    get_response: Response, delete_response: Response
) -> None:
    """Checks that virtual lab in the response of get and delete endpoints are the same."""
    delete_body = copy.deepcopy(cast(dict[str, Any], delete_response.json()))

    get_body = copy.deepcopy(cast(dict[str, Any], get_response.json()))
    get_body.pop("admins", None)
    get_body.pop("created_by", None)

    assert delete_body == get_body
