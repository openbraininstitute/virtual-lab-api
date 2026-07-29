from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_subscriptions_envelope(
    async_test_client: AsyncClient, maintainer_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        "/admin/subscriptions", headers=maintainer_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert {"data", "pagination"} <= body.keys()
    for item in body["data"]:
        assert {"id", "status", "type", "user_id"} <= item.keys()


@pytest.mark.asyncio
async def test_subscription_filters_and_missing_id(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    filtered = await async_test_client.get(
        "/admin/subscriptions",
        params={"subscription_type": "free", "user_id": str(uuid4())},
        headers=admin_headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] == 0

    missing = await async_test_client.get(
        f"/admin/subscriptions/{uuid4()}", headers=admin_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_cancel_missing_subscription_is_404(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await async_test_client.post(
        f"/admin/subscriptions/{uuid4()}/cancel",
        json={"reason": "admin test"},
        headers=admin_headers,
    )
    assert response.status_code == 404
