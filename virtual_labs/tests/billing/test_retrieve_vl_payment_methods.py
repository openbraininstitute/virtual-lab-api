from typing import AsyncGenerator

import pytest
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import cleanup_resources


@pytest.mark.asyncio
async def test_retrieve_vl_payment_methods(
    async_test_client: AsyncClient,
    mock_create_payment_methods: tuple[Response, dict[str, str]],
) -> AsyncGenerator[None, None]:
    client = async_test_client
    (virtual_lab_id, payment_methods) = mock_create_payment_methods

    response = await client.get(
        f"/virtual-labs/{virtual_lab_id}/billing/payment_methods",
    )

    assert response is not None
    assert response.status_code == 200
    assert response.json()["data"]["virtual_lab_id"] == virtual_lab_id
    assert len(response.json()["data"]["payment_methods"]) == len(payment_methods)

    yield None

    await cleanup_resources(client=async_test_client, lab_id=virtual_lab_id)
