from typing import cast
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from stripe import PaymentMethod

from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.tests.utils import (
    create_confirmed_setup_intent,
    session_context_factory,
)


@pytest.mark.asyncio
async def test_attach_new_payment_method_to_vl(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
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

    cardholder_name = "test payment method"

    # this is necessary to confirm the payment method
    # usually this will be handled in the frontend when the user provide payment details

    setup_intent = create_confirmed_setup_intent(customer_id)
    payment_method = cast(PaymentMethod, setup_intent.payment_method)

    assert payment_method is not None
    assert payment_method.card is not None

    payload = {
        "name": cardholder_name,
        "email": "cardholder@vlm.com",
        "setupIntentId": setup_intent.id,
    }

    response = await client.post(
        f"/virtual-labs/{virtual_lab_id}/billing/payment-methods",
        json=payload,
    )

    assert response is not None
    assert response.status_code == 200
    assert (
        response.json()["data"]["payment_method"]["cardholder_name"] == cardholder_name
    )

    assert (
        response.json()["data"]["payment_method"]["card_number"]
        == payment_method.card.last4
    )
