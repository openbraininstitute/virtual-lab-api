from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.institutions.conftest import (
    SERVICE_ADMIN_HEADERS,
    create_institution,
)
from virtual_labs.tests.utils import get_headers


@pytest.mark.asyncio
async def test_institution_updated_successfully(
    async_test_client: AsyncClient,
) -> None:
    institution = await create_institution(async_test_client)

    update_body = {
        "name": f"Updated Institution {uuid4()}",
        "contact_email": "updated@institution.org",
    }

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json=update_body,
        headers=SERVICE_ADMIN_HEADERS,
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
    institution = await create_institution(async_test_client)

    update_body = {"name": f"Partial Update {uuid4()}"}

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json=update_body,
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == update_body["name"]
    assert data["contact_email"] == institution["contact_email"]


@pytest.mark.asyncio
async def test_institution_partial_update_email_only(
    async_test_client: AsyncClient,
) -> None:
    institution = await create_institution(async_test_client)

    update_body = {"contact_email": "newemail@institution.org"}

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json=update_body,
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == institution["name"]
    assert data["contact_email"] == update_body["contact_email"]


@pytest.mark.asyncio
async def test_institution_update_fails_with_empty_body(
    async_test_client: AsyncClient,
) -> None:
    institution = await create_institution(async_test_client)

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json={},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_institution_update_fails_with_duplicate_name(
    async_test_client: AsyncClient,
) -> None:
    institution_a = await create_institution(async_test_client)
    institution_b = await create_institution(async_test_client)

    response = await async_test_client.patch(
        f"/institutions/{institution_b['id']}",
        json={"name": institution_a["name"]},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_institution_update_fails_for_nonexistent_id(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.patch(
        f"/institutions/{uuid4()}",
        json={"name": "Does not matter"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_institution_update_fails_with_invalid_email(
    async_test_client: AsyncClient,
) -> None:
    institution = await create_institution(async_test_client)

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json={"contact_email": "not-an-email"},
        headers=SERVICE_ADMIN_HEADERS,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_update_fails_for_non_admin_user(
    async_test_client: AsyncClient,
) -> None:
    institution = await create_institution(async_test_client)
    headers = get_headers()  # regular "test" user

    response = await async_test_client.patch(
        f"/institutions/{institution['id']}",
        json={"name": "Should Not Work"},
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_institution_update_fails_without_auth(
    async_test_client: AsyncClient,
) -> None:
    response = await async_test_client.patch(
        f"/institutions/{uuid4()}",
        json={"name": "No Auth"},
        headers={"Content-Type": "application/json", "Authorization": ""},
    )

    assert response.status_code == 401
