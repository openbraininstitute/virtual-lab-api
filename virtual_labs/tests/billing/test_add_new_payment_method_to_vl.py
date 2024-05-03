from typing import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient

from virtual_labs.tests.utils import cleanup_resources


@pytest.mark.asyncio
async def test_add_new_payment_method_to_vl(
    async_test_client: AsyncClient,
    mock_create_lab: tuple[str, dict[str, str]],
) -> AsyncGenerator[None, None]:
    client = async_test_client
    (virtual_lab_id, headers) = mock_create_lab

    cardholder_name = "test payment_method"
    payload = {
        "customerId": f"cus_{uuid4()}",
        "name": cardholder_name,
        "email": "cardholder@vlm.com",
        "expireAt": "12/2034",
        "paymentMethodId": f"pm_{uuid4()}",
        "brand": "visa",
        "last4": "4351",
    }

    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/billing/payment_methods",
        json=payload,
    )

    assert response is not None
    assert response.status_code == 200
    assert (
        response.json()["data"]["payment_method"]["cardholder_name"] == cardholder_name
    )

    yield None

    await cleanup_resources(client=async_test_client, lab_id=virtual_lab_id)
