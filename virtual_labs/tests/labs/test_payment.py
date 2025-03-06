import json
import time
from typing import Any, AsyncGenerator

import pytest_asyncio
import stripe
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import session_pool
from virtual_labs.infrastructure.settings import settings

AMOUNT = 1999
BUDGET = 19.99
PAYMENT_EVENT: dict[str, Any] = {
    "api_version": "2024-04-10",
    "created": 1714666059,
    "data": {
        "object": {
            "amount": AMOUNT,
            "amount_capturable": 0,
            "amount_details": {"tip": {}},
            "amount_received": AMOUNT,
            "capture_method": "automatic_async",
            "client_secret": "pi_FOO_secret_BAR",
            "confirmation_method": "automatic",
            "created": 1714666059,
            "currency": "usd",
            "description": "(created by Stripe CLI)",
            "id": "pi_3PC2AZFE4Bi50cLl0pE0hsbR",
            "latest_charge": "ch_3PC2AZFE4Bi50cLl0NU1c9wN",
            "livemode": False,
            "metadata": {},
            "object": "payment_intent",
            "payment_method": "pm_1PC2AZFE4Bi50cLlmzQKPmxp",
            "payment_method_options": {"card": {"request_three_d_secure": "automatic"}},
            "payment_method_types": ["card"],
            "shipping": {
                "address": {
                    "city": "San Francisco",
                    "country": "US",
                    "line1": "510 Townsend St",
                    "postal_code": "94103",
                    "state": "CA",
                },
                "name": "Jenny Rosen",
            },
            "status": "succeeded",
        }
    },
    "id": "evt_3PC2AZFE4Bi50cLl03LCDWpm",
    "livemode": False,
    "object": "event",
    "pending_webhooks": 2,
    "request": {
        "id": "req_q8eaVInO7pceeI",
        "idempotency_key": "7e18b1b0-66e6-4a2d-bc3a-f37b4d2d44a8",
    },
    "type": "payment_intent.succeeded",
}


def _generate_header(payload: str) -> str:
    timestamp = int(time.time())
    scheme = stripe.WebhookSignature.EXPECTED_SCHEME
    payload_to_sign = f"{timestamp}.{payload}"
    signature = stripe.WebhookSignature._compute_signature(  # type: ignore
        payload_to_sign, settings.STRIPE_WEBHOOK_SECRET
    )
    header = f"t={timestamp},{scheme}={signature}"
    return header


@pytest_asyncio.fixture
async def mock_payment_event(
    async_test_client: AsyncClient,
    mock_lab_create: tuple[Response, dict[str, str]],
) -> AsyncGenerator[tuple[dict[str, Any], Response, AsyncClient, dict[str, str]], None]:
    client = async_test_client
    vl_response, headers = mock_lab_create
    lab_id = vl_response.json()["data"]["virtual_lab"]["id"]
    PAYMENT_EVENT["data"]["object"]["metadata"]["vlab"] = lab_id
    body = json.dumps(PAYMENT_EVENT)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "stripe-signature": _generate_header(body),
    }
    response = await client.post(
        "/payments/webhook",
        content=body,
        headers=headers,
    )

    yield PAYMENT_EVENT, response, client, headers


@pytest_asyncio.fixture()
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with session_pool.session() as session:
        yield session
