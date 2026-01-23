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
async def test_update_lab_compute_cell_service_admin_endpoint_forbidden(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    """Test that regular users cannot access the service admin compute_cell endpoint"""
    client, lab_id, headers = mock_lab_create

    update_body = {
        "compute_cell": "cell_b",
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


@pytest.mark.asyncio
async def test_regular_update_does_not_change_compute_cell(
    mock_lab_create: tuple[AsyncClient, str, dict[str, str]],
) -> None:
    """Test that the regular PATCH endpoint ignores compute_cell field"""
    client, lab_id, headers = mock_lab_create

    get_response = await client.get(f"/virtual-labs/{lab_id}", headers=headers)
    assert get_response.status_code == 200
    initial_compute_cell = get_response.json()["data"]["virtual_lab"]["compute_cell"]

    update_body = {
        "name": "Updated Name",
        "compute_cell": "cell_b",  # this should be ignored
    }
    response = await client.patch(
        f"/virtual-labs/{lab_id}", headers=headers, json=update_body
    )
    assert response.status_code == 200
    data = response.json()["data"]["virtual_lab"]
    assert data["name"] == "Updated Name"
    assert data["compute_cell"] == initial_compute_cell  # should remain unchanged


@pytest.mark.asyncio
async def test_update_compute_cell_nonexistent_lab_returns_403(
    async_test_client: AsyncClient,
) -> None:
    """Test that updating compute_cell for a non-existent lab returns 403 for regular users"""
    client = async_test_client
    headers = get_headers()
    nonexistent_lab_id = uuid4()

    update_body = {
        "compute_cell": "cell_b",
    }
    response = await client.patch(
        f"/virtual-labs/{nonexistent_lab_id}/compute-cell",
        headers=headers,
        json=update_body,
    )
    # Should return 403 (forbidden) since auth check happens before existence check
    # Regular users can't access this endpoint at all
    assert response.status_code == 403
