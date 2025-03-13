from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from requests import get

from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    create_paid_subscription_for_user,
    email_server_baseurl,
    get_headers,
    get_invite_token_from_email_body,
    get_user_id_from_test_auth,
)


@pytest_asyncio.fixture
async def mock_lab_invite(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, str, str], None]:
    lab_response = await create_mock_lab(async_test_client)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]
    headers = get_headers("test")

    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    invitee_username = "test-2"
    invitee_email = "test-2@test.com"
    invite = {"email": invitee_email, "role": "admin"}
    invite_response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/invites", headers=headers, json=invite
    )
    assert invite_response.status_code == 200

    yield async_test_client, lab_id, invitee_username, invitee_email

    await cleanup_resources(client=async_test_client, lab_id=lab_id)


def get_invite_token_from_email(recipient_email: str) -> str:
    email_body = get(
        f"{email_server_baseurl}/view/latest.html?query=to:{recipient_email}"
    ).text

    encoded_invite_token = get_invite_token_from_email_body(email_body)
    return encoded_invite_token


@pytest.mark.asyncio
async def test_get_lab_invite_details(
    mock_lab_invite: tuple[AsyncClient, str, str, str],
) -> None:
    client, lab_id, invitee_username, invitee_email = mock_lab_invite
    invite_token = get_invite_token_from_email(invitee_email)
    response = await client.get(
        f"/invites?token={invite_token}", headers=get_headers(username=invitee_username)
    )
    assert response.status_code == 200

    actual_data = response.json()["data"]

    assert actual_data["inviter_full_name"] == "test test"

    assert actual_data["origin"] == "Lab"

    assert actual_data["project_id"] is None
    assert actual_data["project_name"] is None

    assert actual_data["virtual_lab_id"] == lab_id
    assert "Test Lab " in actual_data["virtual_lab_name"]
