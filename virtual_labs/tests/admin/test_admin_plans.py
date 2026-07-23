import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_tiers(
    async_test_client: AsyncClient, maintainer_headers: dict[str, str]
) -> None:
    response = await async_test_client.get("/admin/plans", headers=maintainer_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_tier_round_trip(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    tiers = (await async_test_client.get("/admin/plans", headers=admin_headers)).json()
    if not tiers:
        pytest.skip("no subscription tiers seeded (run populate-tiers)")

    tier = tiers[0]
    original = tier["description"]

    updated = await async_test_client.patch(
        f"/admin/plans/{tier['id']}",
        json={"description": "updated by admin test"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated by admin test"

    restored = await async_test_client.patch(
        f"/admin/plans/{tier['id']}",
        json={"description": original},
        headers=admin_headers,
    )
    assert restored.status_code == 200
    assert restored.json()["description"] == original


@pytest.mark.asyncio
async def test_update_tier_requires_fields(
    async_test_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    tiers = (await async_test_client.get("/admin/plans", headers=admin_headers)).json()
    if not tiers:
        pytest.skip("no subscription tiers seeded (run populate-tiers)")

    response = await async_test_client.patch(
        f"/admin/plans/{tiers[0]['id']}", json={}, headers=admin_headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_credit_rates(
    async_test_client: AsyncClient, maintainer_headers: dict[str, str]
) -> None:
    response = await async_test_client.get(
        "/admin/credit-rates", headers=maintainer_headers
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
