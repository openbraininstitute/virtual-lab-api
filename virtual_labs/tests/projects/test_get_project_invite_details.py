from http import HTTPStatus
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from requests import get

from virtual_labs.tests.utils import (
    create_paid_subscription_for_user,
    email_server_baseurl,
    get_headers,
    get_invite_token_from_email_body,
    get_user_id_from_test_auth,
)


@pytest_asyncio.fixture
async def mock_project_invite(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> AsyncGenerator[tuple[AsyncClient, str, str, str, str], None]:
    client = async_test_client
    response, headers, _ = mock_create_project
    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]
    invitee_email = "test-1@test.com"
    invitee_username = "test-1"
    invite_payload = {"email": f"{invitee_email}", "role": "member"}

    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )
    assert response.status_code == HTTPStatus.OK

    yield client, lab_id, project_id, invitee_email, invitee_username


def get_invite_token_from_email(recipient_email: str) -> str:
    email_body = get(
        f"{email_server_baseurl}/view/latest.html?query=to:{recipient_email}"
    ).text

    encoded_invite_token = get_invite_token_from_email_body(email_body)
    return encoded_invite_token


@pytest.mark.asyncio
async def test_get_lab_invite_details(
    mock_project_invite: tuple[AsyncClient, str, str, str, str],
) -> None:
    client, lab_id, project_id, invitee_email, invitee_username = mock_project_invite
    invite_token = get_invite_token_from_email(invitee_email)
    response = await client.get(
        f"/invites?token={invite_token}", headers=get_headers(username=invitee_username)
    )
    assert response.status_code == 200

    actual_data = response.json()["data"]

    assert actual_data["inviter_full_name"] == "test test"

    assert actual_data["origin"] == "Project"

    assert actual_data["project_id"] == project_id
    assert "Test Project " in actual_data["project_name"]

    assert actual_data["virtual_lab_id"] == lab_id
    assert "Test Lab " in actual_data["virtual_lab_name"]
