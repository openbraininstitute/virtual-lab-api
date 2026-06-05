from uuid import uuid4

import pytest
from httpx import AsyncClient

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

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
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
    body = {
        "contact_email": "contact@institution.org",
    }

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_creation_fails_without_contact_email(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Institution {uuid4()}",
    }

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_institution_creation_fails_with_invalid_email(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    body = {
        "name": f"Test Institution {uuid4()}",
        "contact_email": "not-an-email",
    }

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
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
        headers={
            "Content-Type": "application/json",
            "Authorization": "",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_institution_creation_fails_with_duplicate_name(
    async_test_client: AsyncClient,
) -> None:
    headers = get_headers()
    name = f"Test Institution {uuid4()}"
    body = {
        "name": name,
        "contact_email": "contact@institution.org",
    }

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
    )
    assert response.status_code == 200

    response = await async_test_client.post(
        "/institutions",
        json=body,
        headers=headers,
    )
    assert response.status_code == 409
