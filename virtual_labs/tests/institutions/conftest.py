"""Shared fixtures and helpers for institution tests."""

from uuid import uuid4

from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers

SERVICE_ADMIN_HEADERS = get_headers("test-service-admin")


async def create_institution(client: AsyncClient, name: str | None = None) -> dict:
    """Create an institution and return its data."""
    body = {
        "name": name or f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }
    response = await client.post(
        "/institutions", json=body, headers=SERVICE_ADMIN_HEADERS
    )
    assert response.status_code == 200
    return response.json()["data"]
