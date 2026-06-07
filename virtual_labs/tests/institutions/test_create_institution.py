from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.institutions.conftest import (
    mock_admin_userinfo,
    mock_non_admin_userinfo,
)
from virtual_labs.tests.utils import get_headers


@pytest.mark.asyncio
async def test_institution_created_successfully(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == body["name"]
    assert data["contact_email"] == body["contact_email"]
    assert "id" in data


@pytest.mark.asyncio
async def test_institution_creation_fails_without_name(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {"contact_email": "contact@institution.org"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_creation_fails_without_contact_email(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {"name": f"Test Institution {uuid4()}"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_creation_fails_with_invalid_email(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {"name": f"Test Institution {uuid4()}", "contact_email": "not-an-email"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo
        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_creation_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    body = {
        "name": f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_institution_creation_fails_for_non_admin_user(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_non_admin_userinfo
        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_institution_creation_returns_existing_on_duplicate_name(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    name = f"Test Institution {uuid4()}"
    body = {"name": name, "contact_email": "contact@institution.org"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = mock_admin_userinfo

        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )
        assert response.status_code == 200
        first_id = response.json()["data"]["id"]

        response = await async_test_client.post(
            "/institutions", json=body, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["id"] == first_id
