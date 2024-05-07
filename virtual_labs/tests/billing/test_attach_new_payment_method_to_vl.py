import pytest
from httpx import AsyncClient, Response

from virtual_labs.tests.utils import create_confirmed_setup_intent


@pytest.mark.asyncio
async def test_attach_new_payment_method_to_vl(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> None:
    client = async_test_client
    response, headers = mock_lab_create
    virtual_lab_id = response.json()["data"]["virtual_lab"]["id"]

    cardholder_name = "test payment method"

    # this is required to confirm the payment method
    # usually this will be handled in the frontend when the user provide payment details
    setup_intent_id = create_confirmed_setup_intent()
    payload = {
        "name": cardholder_name,
        "email": "cardholder@vlm.com",
        "setupIntentId": setup_intent_id,
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
