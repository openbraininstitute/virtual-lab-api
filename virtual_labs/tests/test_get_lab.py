import copy
from http import HTTPStatus
from typing import Any, AsyncGenerator, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, dict[str, str], dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "plan_id": 1,
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
    lab_id = lab_create_response.json()["data"]["virtual_lab"]["id"]

    project_body = {
        "name": f"Test Project {uuid4()}",
        "description": "Test",
    }
    project_response = await client.post(
        f"/virtual-labs/{lab_id}/projects",
        json=project_body,
        headers=headers,
    )
    assert project_response.status_code == HTTPStatus.OK

    yield client, lab, headers
    await cleanup_resources(client=client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_get_lab_by_id(
    mock_lab_create: tuple[AsyncClient, dict[str, str], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_create
    lab_id = lab["id"]
    response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert response.status_code == HTTPStatus.OK
    expected_response = {
        "id": lab_id,
        "name": lab["name"],
        "description": lab["description"],
        "reference_email": lab["reference_email"],
        "budget": 0.0,
        "entity": lab["entity"],
        "plan_id": lab["plan_id"],
        "created_at": lab["created_at"],
        "nexus_organization_id": lab["nexus_organization_id"],
        "updated_at": lab["created_at"],
    }
    actual_response = response.json()["data"]["virtual_lab"]
    assert actual_response == expected_response


def assert_get_and_delete_body_are_same(
    get_response: Response, delete_response: Response
) -> None:
    """Checks that virtual lab in the response of get and delete endpoints are the same (except the `deleted` and `deleted_at` values, which will be different)."""
    delete_body = copy.deepcopy(
        cast(dict[str, Any], delete_response.json()["data"]["virtual_lab"])
    )

    get_body = copy.deepcopy(
        cast(dict[str, Any], get_response.json()["data"]["virtual_lab"])
    )

    assert delete_body == get_body


@pytest.mark.asyncio
async def test_get_udpate_delete_response_are_same(
    mock_lab_create: tuple[AsyncClient, dict[str, str], dict[str, str]],
) -> None:
    client, lab, headers = mock_lab_create
    lab_id = lab["id"]
    update_response = await client.patch(
        f"/virtual-labs/{lab_id}", headers=headers, json={"plan_id": 2}
    )
    get_response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)

    assert update_response.status_code == get_response.status_code == HTTPStatus.OK
    assert update_response.json()["data"] == get_response.json()["data"]

    delete_response = await client.delete(f"/virtual-labs/{lab_id}", headers=headers)
    assert delete_response.status_code == get_response.status_code == HTTPStatus.OK
    assert_get_and_delete_body_are_same(get_response, delete_response)
    assert_get_and_delete_body_are_same(get_response, delete_response)
