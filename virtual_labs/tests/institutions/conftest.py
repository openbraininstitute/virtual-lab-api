"""Shared fixtures and helpers for institution tests."""

from unittest.mock import patch
from uuid import uuid4

from httpx import AsyncClient

from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import get_headers


def mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def create_institution(client: AsyncClient, name: str | None = None) -> dict:
    """Create an institution and return its data."""
    headers = get_headers()
    body = {
        "name": name or f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await client.post("/institutions", json=body, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]
