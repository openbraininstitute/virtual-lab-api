from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.shared.groups import VLAB_SERVICE_ADMIN_GROUP
from virtual_labs.tests.utils import get_headers


def _mock_admin_userinfo(*args, **kwargs):
    return {"groups": [VLAB_SERVICE_ADMIN_GROUP]}


def _mock_non_admin_userinfo(*args, **kwargs):
    return {"groups": ["/some-other-group"]}


async def _create_institution(client: AsyncClient, headers: dict) -> dict:
    """Helper to create an institution and return its data."""
    body = {
        "name": f"Test Institution {uuid4()}",
        "contact_email": "contact@institution.org",
    }
    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await client.post("/institutions", json=body, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_institution_updated_successfully(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    update_body = {
        "name": f"Updated Institution {uuid4()}",
        "contact_email": "updated@institution.org",
    }

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == update_body["name"]
    assert data["contact_email"] == update_body["contact_email"]
    assert data["id"] == institution["id"]


@pytest.mark.asyncio
async def test_institution_partial_update_name_only(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    update_body = {"name": f"Partial Update {uuid4()}"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == update_body["name"]
    assert data["contact_email"] == institution["contact_email"]


@pytest.mark.asyncio
async def test_institution_partial_update_email_only(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    update_body = {"contact_email": "newemail@institution.org"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == institution["name"]
    assert data["contact_email"] == update_body["contact_email"]


@pytest.mark.asyncio
async def test_institution_update_fails_with_empty_body(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json={},
            headers=headers,
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_institution_update_fails_with_duplicate_name(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution_a = await _create_institution(async_test_client, headers)
    institution_b = await _create_institution(async_test_client, headers)

    update_body = {"name": institution_a["name"]}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution_b['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_institution_update_fails_for_nonexistent_id(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    fake_id = uuid4()
    update_body = {"name": "Does not matter"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{fake_id}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_institution_update_fails_with_invalid_email(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    update_body = {"contact_email": "not-an-email"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_update_fails_for_non_admin_user(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    institution = await _create_institution(async_test_client, headers)

    update_body = {"name": "Should Not Work"}

    with patch(
        "virtual_labs.core.authorization.verify_service_admin.kc_auth"
    ) as mock_kc:
        mock_kc.userinfo.side_effect = _mock_non_admin_userinfo
        response = await async_test_client.patch(
            f"/institutions/{institution['id']}",
            json=update_body,
            headers=headers,
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_institution_update_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    fake_id = uuid4()
    update_body = {"name": "No Auth"}

    response = await async_test_client.patch(
        f"/institutions/{fake_id}",
        json=update_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401
