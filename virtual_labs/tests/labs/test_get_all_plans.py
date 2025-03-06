import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers


@pytest.mark.asyncio
async def test_get_all_plans(async_test_client: AsyncClient) -> None:
    client = async_test_client
    headers = get_headers()
    response = await client.get("/plans", headers=headers)
    assert response.status_code == 200
    all_plans = response.json()["data"]["all_plans"]
    assert len(all_plans) == 3
