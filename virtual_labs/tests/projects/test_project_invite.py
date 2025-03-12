from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response

from virtual_labs.tests.labs.test_accept_lab_invite import get_invite_token_from_email
from virtual_labs.tests.utils import (
    create_free_subscription_for_user,
    create_paid_subscription_for_user,
    get_headers,
    get_user_id_from_test_auth,
)


@pytest.mark.asyncio
async def test_invite_user_to_project(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project

    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]

    user_to_invite = "test-1"
    invite_payload = {"email": f"{user_to_invite}@test.com", "role": "admin"}

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )
    assert response.status_code == HTTPStatus.OK

    invite_token = get_invite_token_from_email(f"{user_to_invite}@test.com")
    accept_invite_response = await client.post(
        f"/invites?token={invite_token}", headers=get_headers(username=user_to_invite)
    )
    assert accept_invite_response.status_code == HTTPStatus.OK


@pytest.mark.asyncio
async def test_user_already_in_project_cannot_be_reinvited(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project
    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]

    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    user_to_invite = "test-1"
    invite_payload = {"email": f"{user_to_invite}@test.com", "role": "admin"}

    invite_user_response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )
    assert invite_user_response.status_code == HTTPStatus.OK

    invite_token = get_invite_token_from_email(f"{user_to_invite}@test.com")
    await client.post(
        f"/invites?token={invite_token}", headers=get_headers(username=user_to_invite)
    )

    reinvite_user_response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )
    assert reinvite_user_response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_user_not_in_keycloak_can_also_be_invited(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    client = async_test_client
    response, headers, _ = mock_create_project
    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]

    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    user_to_invite = "user-not-in-keycloak"
    invite_payload = {"email": f"{user_to_invite}@test.com", "role": "admin"}

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )
    assert response.status_code == HTTPStatus.OK

    invite_token = get_invite_token_from_email(f"{user_to_invite}@test.com")
    assert invite_token is not None


@pytest.mark.asyncio
async def test_user_without_subscription_cannot_invite(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    """Test that a user without a paid subscription cannot invite others to a project."""
    client = async_test_client
    response, headers, _ = mock_create_project
    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]

    # Note: We deliberately do NOT create a subscription for this user

    user_to_invite = "test-no-subscription"
    invite_payload = {"email": f"{user_to_invite}@test.com", "role": "admin"}

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )

    # The request should be forbidden because the user doesn't have a subscription
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert (
        "User is not allowed to invite users to this project"
        in response.json()["message"]
    )


@pytest.mark.asyncio
async def test_user_with_free_subscription_cannot_invite(
    async_test_client: AsyncClient,
    mock_create_project: tuple[Response, dict[str, str], dict[str, str]],
) -> None:
    """Test that a user with only a free subscription cannot invite others to a project."""
    client = async_test_client
    response, headers, _ = mock_create_project
    lab_id = response.json()["data"]["virtual_lab_id"]
    project_id = response.json()["data"]["project"]["id"]

    # Get the user ID and create a FREE subscription (not paid)
    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_free_subscription_for_user(user_id)

    user_to_invite = "test-free-subscription"
    invite_payload = {"email": f"{user_to_invite}@test.com", "role": "admin"}

    response = await client.post(
        f"/virtual-labs/{lab_id}/projects/{project_id}/invites",
        json=invite_payload,
        headers=headers,
    )

    # The request should be forbidden because the user only has a free subscription
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert (
        "User is not allowed to invite users to this project"
        in response.json()["message"]
    )
