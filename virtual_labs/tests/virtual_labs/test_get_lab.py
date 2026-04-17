import copy
from http import HTTPStatus
from typing import Any, AsyncGenerator, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_without_course(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, dict[str, str], dict[str, str]], None]:
    """Creates a standard virtual lab without a course."""
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
    lab = lab_create_response.json()["data"]["virtual_lab"]

    yield client, lab, headers
    await cleanup_resources(client=client, lab_id=lab["id"])


@pytest_asyncio.fixture
async def mock_lab_with_course(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, dict[str, str], dict[str, str]], None]:
    """Creates a virtual lab with a course configuration."""
    client = async_test_client
    template_project_id = str(uuid4())
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
        "course": {"template_project_id": template_project_id, "is_initialized": False},
    }
    headers = get_headers()
    lab_create_response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    assert lab_create_response.status_code == 200
    lab = lab_create_response.json()["data"]["virtual_lab"]

    yield client, lab, headers
    await cleanup_resources(client=client, lab_id=lab["id"])


@pytest.mark.asyncio
async def test_get_lab_by_id_without_course(
    mock_lab_without_course: tuple[AsyncClient, dict[str, str], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_without_course
    lab_id = lab["id"]

    response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert response.status_code == HTTPStatus.OK

    actual = response.json()["data"]["virtual_lab"]
    assert actual["id"] == lab_id
    assert actual["name"] == lab["name"]
    assert actual["description"] == lab["description"]
    assert actual["reference_email"] == lab["reference_email"]
    assert actual["entity"] == lab["entity"]
    assert actual["created_at"] == lab["created_at"]

    assert actual["course"] is None or actual["course"] == {
        "is_initialized": False,
        "template_project_id": None,
    }


@pytest.mark.asyncio
async def test_get_lab_by_id_with_course(
    mock_lab_with_course: tuple[AsyncClient, dict[str, str], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_with_course
    lab_id = lab["id"]

    response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert response.status_code == HTTPStatus.OK

    actual = response.json()["data"]["virtual_lab"]
    assert actual["id"] == lab_id
    assert actual["name"] == lab["name"]
    assert actual["description"] == lab["description"]
    assert actual["reference_email"] == lab["reference_email"]
    assert actual["entity"] == lab["entity"]
    assert actual["created_at"] == lab["created_at"]

    assert actual["course"] is not None
    assert actual["course"]["is_initialized"] is False


def assert_get_and_delete_body_are_same(
    get_response: Response, delete_response: Response
) -> None:
    """Checks that virtual lab in the response of get and delete endpoints are the same."""
    delete_body = copy.deepcopy(
        cast(dict[str, Any], delete_response.json()["data"]["virtual_lab"])
    )

    get_body = copy.deepcopy(
        cast(dict[str, Any], get_response.json()["data"]["virtual_lab"])
    )

    assert delete_body == get_body
