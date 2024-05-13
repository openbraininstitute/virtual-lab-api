from typing import AsyncGenerator
from uuid import UUID

import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import select

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.tests.utils import (
    create_confirmed_setup_intent,
    session_context_factory,
)


@pytest_asyncio.fixture
async def mock_create_payment_methods(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[str, list[dict[str, str]], dict[str, str]], None]:
    client = async_test_client
    response, headers = mock_lab_create

    virtual_lab_id = response.json()["data"]["virtual_lab"]["id"]
    async with session_context_factory() as session:
        customer_id = (
            await session.execute(
                statement=select(VirtualLab.stripe_customer_id).filter(
                    VirtualLab.id == UUID(virtual_lab_id)
                )
            )
        ).scalar_one()

    payment_methods = [
        {
            "name": f"test payment_method {i}",
            "email": f"cardholder_{i}@vlm.com",
            "setupIntentId": (await create_confirmed_setup_intent(customer_id)).id,
        }
        for i in range(3)
    ]

    for pm in payment_methods:
        await client.post(
            f"/virtual-labs/{virtual_lab_id}/billing/payment-methods",
            json=pm,
        )

    yield virtual_lab_id, payment_methods, headers
