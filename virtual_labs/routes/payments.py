import logging
from http import HTTPStatus
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.stripe import (
    get_stripe_repository,
    get_stripe_webhook_service,
)
from virtual_labs.infrastructure.stripe.webhook import StripeWebhook
from virtual_labs.repositories.stripe_repo import StripeRepository

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
        logger.exception(f"Error processing Stripe webhook: {str(e)}")
        # Always return 200 to Stripe even on error to prevent retries
        return {"success": False, "error": str(e)}
