from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

from virtual_labs.tests.utils import cleanup_resources, get_headers


@pytest_asyncio.fixture
async def mock_lab_create(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[AsyncClient, str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "entity": "EPFL, Switzerland",
        "email_status": "verified",
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

    await cleanup_resources(client=client, lab_id=lab_id)


@pytest.mark.asyncio
async def test_update_lab(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    client, lab_id, headers = mock_lab_create

    update_body = {
        "name": "New Name",
        "entity": "Max Planck",
    }
    response = await client.patch(
        f"/virtual-labs/{lab_id}", headers=headers, json=update_body
    )
    assert response.status_code == 200
    data = response.json()["data"]["virtual_lab"]
    assert data["name"] == update_body["name"]
    assert data["entity"] == update_body["entity"]


@pytest.mark.asyncio
async def test_update_lab_compute_cell_forbidden(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    """Test that regular users cannot update compute_cell field"""
    client, lab_id, headers = mock_lab_create

    update_body = {
        "name": "New Name",
        "compute_cell": "cell-b",
    }
    response = await client.patch(
        f"/virtual-labs/{lab_id}", headers=headers, json=update_body
    )
    assert response.status_code == 403
    error_data = response.json()
    assert error_data["error_code"] == "FORBIDDEN_OPERATION"
    assert "service admins" in error_data["message"].lower()


@pytest.mark.asyncio
async def test_update_lab_compute_cell_service_admin_endpoint_forbidden(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    """Test that regular users cannot access the service admin compute_cell endpoint"""
    client, lab_id, headers = mock_lab_create

    update_body = {
        "compute_cell": "cell-b",
    }
    response = await client.patch(
        f"/virtual-labs/{lab_id}/compute-cell", headers=headers, json=update_body
    )
    assert response.status_code == 403
    error_data = response.json()
    assert error_data["error_code"] == "AUTHORIZATION_ERROR"
    assert (
        "administrative" in error_data.get("details", "").lower()
        or "admin" in error_data.get("message", "").lower()
    )
