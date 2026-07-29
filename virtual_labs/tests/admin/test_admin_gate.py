"""Role-matrix for the `/admin` namespace gates.

Reads require admin or maintainer; writes require admin. The write
probe targets a random lab id: passing the gate surfaces a 404 from
the usecase, while a denial short-circuits to 401/403 before any
lookup happens.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

UPDATE_BODY = {"description": "updated by admin gate test"}


@pytest.mark.asyncio
async def test_admin_has_read_and_write_access(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    read = await async_test_client.get("/admin/labs", headers=admin_headers)
    assert read.status_code == 200

    write = await async_test_client.patch(
        f"/admin/labs/{uuid4()}", json=UPDATE_BODY, headers=admin_headers
    )
    assert write.status_code == 404


@pytest.mark.asyncio
async def test_maintainer_has_read_access_only(
    async_test_client: AsyncClient, maintainer_headers: dict[str, str]
) -> None:
    read = await async_test_client.get("/admin/labs", headers=maintainer_headers)
    assert read.status_code == 200

    write = await async_test_client.patch(
        f"/admin/labs/{uuid4()}", json=UPDATE_BODY, headers=maintainer_headers
    )
    assert write.status_code == 403


@pytest.mark.asyncio
async def test_plain_user_is_denied(
    async_test_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    read = await async_test_client.get("/admin/labs", headers=user_headers)
    assert read.status_code == 403

    write = await async_test_client.patch(
        f"/admin/labs/{uuid4()}", json=UPDATE_BODY, headers=user_headers
    )
    assert write.status_code == 403


@pytest.mark.asyncio
async def test_missing_token_is_unauthorized(async_test_client: AsyncClient) -> None:
    response = await async_test_client.get("/admin/labs", headers={"Authorization": ""})
    assert response.status_code == 401
