from typing import AsyncGenerator

import pytest
from httpx import AsyncClient

from virtual_labs.infrastructure.stripe.config import test_stripe_client
from virtual_labs.tests.utils import cleanup_resources


@pytest.mark.asyncio
async def test_attach_new_payment_method_to_vl(
    async_test_client: AsyncClient,
    mock_create_lab: tuple[str, dict[str, str]],
) -> AsyncGenerator[None, None]:
    client = async_test_client
    (virtual_lab_id, headers) = mock_create_lab

    cardholder_name = "test payment_method"
    # this is required to confirm the payment method
    # usually this will be handled in the frontend when the user provide payment details

    setup_intent = test_stripe_client.setup_intents.create()
    setup_intent_confirmed = test_stripe_client.setup_intents.confirm(
        setup_intent.id,
        {
            "return_url": "http://localhost:4000",
            "payment_method": "pm_card_visa",
        },
    )

    payload = {
        "name": cardholder_name,
        "email": "cardholder@vlm.com",
        "setupIntentId": setup_intent_confirmed.id,
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
