from http import HTTPStatus
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.labs import topup_virtual_lab

router = APIRouter(prefix="/payments", tags=["Payments"])


async def _get_body(request: Request) -> bytes:
    return await request.body()


@router.post(
    "/webhook",
    operation_id="payment_processor",
    summary="This will process the payment event",
    response_model=None,
    status_code=HTTPStatus.NO_CONTENT,
    include_in_schema=False,
)
async def handle_payment_event(
    stripe_signature: Annotated[str, Header(alias="stripe-signature")],
    db: AsyncSession = Depends(default_session_factory),
    body: bytes = Depends(_get_body),
) -> None:
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(body, stripe_signature, endpoint_secret)  # type: ignore
    except ValueError as e:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST) from e
    except stripe.SignatureVerificationError as e:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY) from e

    if event["type"] == "payment_intent.succeeded":
        intent_object = event["data"]["object"]
        lab_id = intent_object["metadata"]["vlab"]
        amount_received = intent_object["amount_received"]
        stripe_event_id = event["id"]
        await topup_virtual_lab(db, lab_id, amount_received, stripe_event_id)
