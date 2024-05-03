from typing import AsyncGenerator
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import get_headers


@pytest_asyncio.fixture
async def mock_create_lab(
    async_test_client: AsyncClient,
) -> AsyncGenerator[tuple[str, dict[str, str]], None]:
    client = async_test_client
    body = {
        "name": f"Test Lab {uuid4()}",
        "description": "Test",
        "reference_email": "user@test.org",
        "budget": 10000,
        "plan_id": 1,
        "entity": "EPFL, Switzerland",
    }
    headers = get_headers()
    response = await client.post(
        "/virtual-labs",
        json=body,
        headers=headers,
    )
    lab_id = response.json()["data"]["virtual_lab"]["id"]

    yield lab_id, headers


@pytest_asyncio.fixture
async def mock_create_payment_methods(
    async_test_client: AsyncClient,
    mock_create_lab: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[Response, list[dict[str, str]], dict[str, str]], None]:
    client = async_test_client
    virtual_lab_id, headers = mock_create_lab

    payment_methods = [
        {
            "customerId": f"cus_{uuid4()}",
            "name": f"test payment_method {i}",
            "email": f"cardholder_{i}@vlm.com",
            "expireAt": "12/2034",
            "paymentMethodId": f"pm_{uuid4()}",
            "brand": "visa",
            "last4": f"435{i}",
        }
        for i in range(3)
    ]

    for pm in payment_methods:
        await client.post(
            f"/virtual-labs/{virtual_lab_id}/billing/payment_methods",
            json=pm,
        )

    yield virtual_lab_id, payment_methods, headers
