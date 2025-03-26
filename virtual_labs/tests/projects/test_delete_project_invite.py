from http import HTTPStatus
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.labs.test_accept_lab_invite import get_invite_token_from_email
from virtual_labs.tests.utils import (
    create_paid_subscription_for_user,
    get_headers,
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


@pytest.mark.asyncio
async def test_cancel_invite_cannot_be_accepted(
    mock_project_invite: tuple[AsyncClient, str, str, str, str],
) -> None:
    client, lab_id, project_id, invitee_email, invitee_username = mock_project_invite
    delete_invite_response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites/cancel",
        headers=get_headers(),
        json={"email": invitee_email, "role": "member"},
    )
    assert delete_invite_response.status_code == HTTPStatus.OK

    invite_token = get_invite_token_from_email(invitee_email)
    accept_invite_response = await client.post(
        f"/invites?token={invite_token}", headers=get_headers(username=invitee_username)
    )
    assert accept_invite_response.status_code == HTTPStatus.NOT_FOUND
    assert (
        accept_invite_response.json()["message"] == "No invite was found for this link"
    )
