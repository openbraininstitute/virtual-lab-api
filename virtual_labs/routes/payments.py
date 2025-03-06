import logging
from http import HTTPStatus
from textwrap import dedent
from typing import Annotated, Any, Dict, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.payment_method import SetupIntentOut
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import (
    get_stripe_repository,
    get_stripe_webhook_service,
)
from virtual_labs.infrastructure.stripe.webhook import StripeWebhook
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.usecases import payment as payment_cases

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


async def _get_body(request: Request) -> bytes:
    return await request.body()


@router.post(
    "/webhook",
    operation_id="stripe_webhook_handler",
    summary="Process all Stripe webhook events",
    response_model=Dict[str, Any],
    status_code=HTTPStatus.OK,
)
async def handle_stripe_webhook(
    stripe_signature: Annotated[str, Header(alias="Stripe-Signature")],
    db: AsyncSession = Depends(default_session_factory),
    webhook_service: StripeWebhook = Depends(get_stripe_webhook_service),
    stripe_service: StripeRepository = Depends(get_stripe_repository),
    body: bytes = Depends(_get_body),
) -> Dict[str, Any]:
    """
    webhook handler for all necessary events.

    This endpoint handles:
    1. virtual lab topup payments (when metadata contains topup_balance=true)
    2. subscription related events (recurring payments)
    """

    try:
        # verify webhook signature
        event = await stripe_service.construct_event(body, stripe_signature)

        if not event:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="Invalid Stripe webhook signature",
            )

        event_type = event.get("type", "")
        event_id = event.get("id", "")

        logger.info(f"Processing Stripe webhook event: {event_type} (ID: {event_id})")

        if (
            event_type in webhook_service.subscription_update_events
            or event_type in webhook_service.payment_update_events
            or event_type in webhook_service.standalone_payment_events
        ):
            result = await webhook_service.handle_webhook_event(event, db)

            return {
                "success": True,
                "result": {**result, "payment_type": "subscription"},
            }

        # For any other events, just log and acknowledge
        logger.info(f"Received unhandled event type: {event_type}")
        return {
            "success": True,
            "result": {
                "status": "ignored",
                "event_type": event_type,
                "message": "Event type not handled",
            },
        }

    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {str(e)}")
        # Always return 200 to Stripe even on error to prevent retries
        return {"success": False, "error": str(e)}


@router.get(
    "/setup-intent",
    operation_id="generate_setup_intent",
    summary="Generate setup intent for the authenticated user",
    description=dedent(
        """
    This endpoint checks if the user has a Stripe customer ID and creates one if needed.
    It then generates a setup intent that can be used to add payment methods securely.

    To confirm the setup intent without using the frontend app, you can access the stripe api docs
    and use the builtin-CLI to confirm the setup intent id.

    ### Stripe dashboard CLI
    You have to use test mode of the stripe account 
    [Stripe Builtin-CLI](https://docs.stripe.com/api/setup_intents/confirm?shell=true&api=true&resource=setup_intents&action=confirm) 

    ### Local machine Stripe CLI

    ```shell 
    stripe setup_intents confirm {setup_intent_id} --payment-method={payment_method}
    ```
    where:
    ```py
    setup_intent_id = `seti_1Mm2cBLkdIwHu7ixaiKW3ElR` # the generated setupIntent 
    payment_method = `pm_card_visa` 
    # it can be any payment method, available in test cards page
    ```

    [Stripe Test cards](https://docs.stripe.com/testing?testing-method=payment-methods)
    """
    ),
    response_model=VliAppResponse[SetupIntentOut],
)
async def generate_setup_intent(
    session: AsyncSession = Depends(default_session_factory),
    auth: Tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> Response:
    return await payment_cases.generate_setup_intent(
        session,
        auth=auth,
    )
