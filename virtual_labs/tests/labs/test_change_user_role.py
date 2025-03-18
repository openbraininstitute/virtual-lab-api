from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from requests import get

from virtual_labs.infrastructure.kc.models import UserRepresentation
from virtual_labs.repositories.user_repo import UserQueryRepository
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab,
    email_server_baseurl,
    get_headers,
    get_invite_token_from_email_body,
)


def get_invite_token_from_email(recipient_email: str) -> str:
    email_body = get(
        f"{email_server_baseurl}/view/latest.html?query=to:{recipient_email}"
    ).text

    encoded_invite_token = get_invite_token_from_email_body(email_body)
    return encoded_invite_token


@pytest_asyncio.fixture
async def mock_lab_invite(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, str, str], None]:
    # Create lab
    lab_response = await create_mock_lab(async_test_client)
    lab_id = lab_response.json()["data"]["virtual_lab"]["id"]
    headers = get_headers("test")

    # Invite a user
    invitee_username = "test-2"
    invitee_email = "test-2@test.com"
    invite = {"email": invitee_email, "role": "admin"}
    invite_response = await async_test_client.post(
        f"/virtual-labs/{lab_id}/invites", headers=headers, json=invite
    )
    assert invite_response.status_code == 200

    # Accept invite
    invite_token = get_invite_token_from_email(invitee_email)
    accept_invite_response = await async_test_client.post(
        f"/invites?token={invite_token}", headers=get_headers(username=invitee_username)
    )
    assert accept_invite_response.status_code == 200

    invitee_id = (
        cast(
            UserRepresentation,
            UserQueryRepository().retrieve_user_by_email(invitee_email),
        )
    ).id

    yield async_test_client, lab_id, invitee_id, invitee_username

    await cleanup_resources(client=async_test_client, lab_id=lab_id)


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
            assert user["role"] == "member"
            assert user["invite_accepted"] is True


@pytest.mark.asyncio
async def test_change_user_role_in_lab(
    mock_lab_invite: tuple[AsyncClient, str, str, str],
) -> None:
    client, lab_id, invitee_id, invitee_username = mock_lab_invite
    response = await client.patch(
        f"virtual-labs/{lab_id}/users/{invitee_id}?new_role=member",
        headers=get_headers(),
    )
    assert response.status_code == 200
    lab_users_response = await client.get(
        f"/virtual-labs/{lab_id}/users", headers=get_headers(invitee_username)
    )
    assert_right_users_in_lab(lab_users_response)
