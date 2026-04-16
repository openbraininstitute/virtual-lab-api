import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import get_headers


@pytest.mark.asyncio
async def test_get_total_users(async_test_client: AsyncClient) -> None:
    client = async_test_client
    headers = get_headers()
    response = await client.get("/users_count", headers=headers)
    assert response.status_code == 200
    total_users = response.json()["data"]["total"]
    assert total_users == 3
