from typing import Any, AsyncGenerator, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[Response, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    yield response, headers

    if response.status_code == 200:
        try:
            lab_id = response.json()["data"]["virtual_lab"]["id"]
            await cleanup_resources(client=client, lab_id=lab_id)
        except Exception:
            pass


@pytest_asyncio.fixture
async def mock_lab_create_with_users(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[dict[str, Any], Response, AsyncClient, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )

    yield body, response, client, headers

    if response.status_code == 200:
        try:
            lab_id = response.json()["data"]["virtual_lab"]["id"]
            await cleanup_resources(client=client, lab_id=lab_id)
        except Exception:
            pass


def assert_users_in_lab(response: Response) -> None:
    users = cast(list[dict[str, Any]], response.json()["data"]["users"])
    actual_users = [
        {
            "username": user.get("username"),
            "invite_accepted": user.get("invite_accepted"),
            "role": user.get("role"),
        }
        for user in users
    ]
    expected_users = [
        {
            "username": "test",
            "invite_accepted": True,
            "role": "admin",
        },
        {
            "username": "test-1",
            "invite_accepted": False,
            "role": "admin",
        },
        {
            "username": "test-2",
            "invite_accepted": False,
            "role": "member",
        },
    ]
    assert actual_users == expected_users


@pytest.mark.asyncio
async def test_virtual_lab_created(
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    response, headers = mock_lab_create
    # Test that the virtual lab was created
    assert response.status_code == 200
    data = response.json()["data"]
    lab_id = data["virtual_lab"]["id"]

    # CreateLabOut only has virtual_lab, no invite fields
    assert data["virtual_lab"] is not None

    group_repo = GroupQueryRepository()
    group_id = f"vlab/{lab_id}/admin"

    # Test that the keycloak admin group was created
    group = group_repo.retrieve_group_by_name(name=group_id)
    assert group is not None
