from typing import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import create_confirmed_setup_intent


@pytest_asyncio.fixture
async def mock_create_payment_methods(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[str, list[dict[str, str]], dict[str, str]], None]:
    client = async_test_client
    response, headers = mock_lab_create

    virtual_lab_id = response.json()["data"]["virtual_lab"]["id"]

    payment_methods = [
        {
            "name": f"test payment_method {i}",
            "email": f"cardholder_{i}@vlm.com",
            "expireAt": "12/2034",
            "setupIntentId": create_confirmed_setup_intent(),
        }
        for i in range(3)
    ]

    for pm in payment_methods:
        await client.post(
            f"/virtual-labs/{virtual_lab_id}/billing/payment-methods",
            json=pm,
        )

    yield virtual_lab_id, payment_methods, headers
