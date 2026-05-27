import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.infrastructure.settings import settings
from virtual_labs.tests.utils import (
    cleanup_resources,
    create_mock_lab_with_project,
    create_paid_subscription_for_user,
    get_headers,
    get_user_id_from_test_auth,
)
from virtual_labs.usecases.invites.webhook_handler import compute_webhook_signature

WEBHOOK_SECRET = "test_webhook_secret_hex_value"


def sign(body: bytes) -> str:
    """Compute a valid signature for the test webhook secret."""
    return compute_webhook_signature(body, WEBHOOK_SECRET)


@pytest_asyncio.fixture(autouse=True)
async def set_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "INVITE_WEBHOOK_SECRET", WEBHOOK_SECRET)


@pytest_asyncio.fixture
async def lab_and_project(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, str, str], None]:
    """Create a virtual lab with a project for testing. Returns (lab_id, project_id, user_id)."""
    headers = get_headers("test")
    user_id = await get_user_id_from_test_auth(
        auth_header=headers.get("Authorization", "")
    )
    await create_paid_subscription_for_user(user_id)

    lab, project_id = await create_mock_lab_with_project(async_test_client)
    lab_id = lab["id"]

    yield lab_id, project_id, str(user_id)

    await cleanup_resources(client=async_test_client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_webhook_successful_invite(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, project_id, user_id = lab_and_project

    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": project_id,
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Invite sent successfully"
    assert data["invitee_email"] == "invitee@example.com"
    assert data["invitee_name"] == "Test Invitee"


@pytest.mark.asyncio
async def test_webhook_invalid_signature(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, project_id, user_id = lab_and_project

    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "invalid_signature",
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": project_id,
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_missing_signature_header(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, project_id, user_id = lab_and_project

    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": project_id,
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_missing_virtual_lab_id_header(
    async_test_client: AsyncClient,
) -> None:
    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Project-Id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "X-User-Id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_invalid_uuid_in_header(
    async_test_client: AsyncClient,
) -> None:
    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Virtual-Lab-Id": "not-a-uuid",
            "X-Project-Id": "also-not-a-uuid",
            "X-User-Id": "not-a-uuid-either",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_invalid_email_in_body(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, project_id, user_id = lab_and_project

    payload = {"name": "Test Invitee", "email": "not-an-email"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": project_id,
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_project_not_found(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, _, user_id = lab_and_project

    payload = {"name": "Test Invitee", "email": "invitee@example.com"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_webhook_missing_body_fields(
    async_test_client: AsyncClient,
    lab_and_project: tuple[str, str, str],
) -> None:
    lab_id, project_id, user_id = lab_and_project

    payload = {"name": "Test Invitee"}
    body = json.dumps(payload).encode("utf-8")
    signature = sign(body)

    response = await async_test_client.post(
        "/invites/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Virtual-Lab-Id": lab_id,
            "X-Project-Id": project_id,
            "X-User-Id": user_id,
        },
    )

    assert response.status_code == 422
