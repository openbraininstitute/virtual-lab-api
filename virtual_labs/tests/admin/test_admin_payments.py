from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_payments_envelope(
    async_test_client: AsyncClient, maintainer_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        "/admin/payments", headers=maintainer_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert {"total_count", "payments", "current_page"} <= body.keys()


@pytest.mark.asyncio
async def test_list_payments_for_user_without_stripe_customer(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        "/admin/payments", params={"user_id": str(uuid4())}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["total_count"] == 0


@pytest.mark.asyncio
async def test_get_missing_payment_is_404(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        f"/admin/payments/{uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404
