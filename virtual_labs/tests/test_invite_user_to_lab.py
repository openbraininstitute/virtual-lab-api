from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import get_headers


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "budget": 10,
        "plan_id": 1,
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )
    assert response.status_code == 200
    lab_id = response.json()["data"]["virtual_lab"]["id"]
    yield client, lab_id, headers

    lab_id = response.json()["data"]["virtual_lab"]["id"]
    response = await client.delete(f"/virtual-labs/{lab_id}", headers=get_headers())
    assert response.status_code == 200


def assert_invite_response(response: Response) -> None:
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Invite sent to user"
    assert data["data"]["invite_id"] is not None


def assert_right_users_in_lab(response: Response) -> None:
    assert response.status_code == 200
    lab_users_response_data = response.json()
    lab_users = lab_users_response_data["data"]["users"]
    assert len(lab_users) == 2
    for user in lab_users:
        if user["username"] == "test":
            assert user["role"] == "admin"
            assert user["invite_accepted"] is True
        else:
            assert user["username"] == "test-2"
            assert user["role"] == "admin"
            assert user["invite_accepted"] is False


@pytest.mark.asyncio
async def test_invite_user_to_lab(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    client, lab_id, headers = mock_lab_create

    invite = {"email": "test-2@test.com", "role": "admin"}
    invite_response = await client.post(
        f"/virtual-labs/{lab_id}/invites", headers=headers, json=invite
    )
    assert_invite_response(invite_response)

    lab_users_response = await client.get(
        f"/virtual-labs/{lab_id}/users", headers=headers
    )
    assert_right_users_in_lab(lab_users_response)
