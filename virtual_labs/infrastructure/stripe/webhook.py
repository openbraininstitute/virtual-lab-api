from datetime import datetime
from typing import Any, Dict, Optional

import stripe
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    PaymentStatus,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
)
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


class StripeWebhook:
    """
    module for handling Stripe webhook events and updating database records.
    """

    # Event types that require subscription updates
    subscription_update_events = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.pending_update_applied",
        "customer.subscription.pending_update_expired",
    }

    # Event types that require payment updates
    payment_update_events = {
        "invoice.payment_succeeded",
        "invoice.payment_failed",
        "invoice.paid",
        "charge.succeeded",
        "charge.failed",
        "charge.refunded",
        "charge.dispute.created",
    }

    def __init__(
        self,
        stripe_repository: StripeRepository,
        subscription_repository: SubscriptionRepository,
    ):
        self.stripe_repository = stripe_repository
        self.subscription_repository = subscription_repository

    async def handle_webhook_event(
        self, event_json: stripe.Event, db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handling webhook events.
        groups events by type.

        Args:
            event_json: raw event json from Stripe
            db_session: db session for persistence

        Returns:
            Dict with processing results
        """
        try:
            event_type = event_json.get("type")
            event_id = event_json.get("id")

            logger.info(
                f"Processing Stripe webhook event: {event_type} (ID: {event_id})"
            )

            # Group events by category for efficient processing
            if event_type in self.subscription_update_events:
                return await self._handle_subscription_event(event_json, db_session)
            elif event_type in self.payment_update_events:
                return await self._handle_payment_event(event_json, db_session)
            else:
                logger.info(f"Ignoring unhandled event type: {event_type}")
                return {
                    "status": "ignored",
                    "event_type": event_type,
                }

        except Exception as e:
            logger.exception(f"Error processing webhook event: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
            }

    async def _handle_subscription_event(
        self, event_json: Dict[str, Any], db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handle subscription related events by fetching the latest subscription data
        and updating the database.
        """
        event_type = event_json.get("type")
        subscription_id = event_json.get("data", {}).get("object", {}).get("id")

        if not subscription_id:
            logger.warning(f"No subscription ID found in event: {event_type}")
            return {
                "status": "error",
                "message": "No subscription ID in event",
            }

        # fetch the latest subscription data from Stripe
        stripe_subscription = await self.stripe_repository.get_subscription(
            subscription_id
        )

        if not stripe_subscription:
            logger.warning(
                f"Could not fetch subscription {subscription_id} from Stripe"
            )
            return {"status": "error", "message": "Subscription not found in Stripe"}

        # update or create subscription record
        await self._update_subscription_record(stripe_subscription, db_session)

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _handle_payment_event(
        self, event_json: Dict[str, Any], db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handle payment related events by updating payment records.
        """
        event_type: str = str(event_json.get("type"))
        event_data: Dict[str, Any] = event_json.get("data", {}).get("object", {})

        # different event types have different structures
        if "invoice" in event_type:
            subscription_id = event_data.get("subscription")
            payment_intent_id = event_data.get("payment_intent")
            invoice_id = event_data.get("id")
        elif "charge" in event_type:
            payment_intent_id = event_data.get("payment_intent")
            invoice_id = event_data.get("invoice")
            subscription_id = None  # Need to look up via invoice
        else:
            logger.warning(f"Unhandled payment event type: {event_type}")
            return {
                "status": "ignored",
                "event_type": event_type,
            }

        if invoice_id and not subscription_id:
            invoice = await self.stripe_repository.get_invoice(invoice_id)
            if invoice:
                subscription_id = invoice.get("subscription")

        if not subscription_id:
            logger.warning(
                f"Could not determine subscription ID for event: {event_type}"
            )
            return {
                "status": "error",
                "message": "No subscription ID found",
            }

        # fetch the latest subscription data
        stripe_subscription = await self.stripe_repository.get_subscription(
            subscription_id
        )

        if not stripe_subscription:
            intent_object = event_data["object"]
            metadata = intent_object.get("metadata", {})
            virtual_lab_id = metadata.get("virtual_lab_id")
            standalone = metadata.get("standalone")
            if virtual_lab_id:
                subscription = await self.subscription_repository.get_active_subscription_by_lab_id(
                    virtual_lab_id
                )
                if subscription:
                    stripe_subscription = await self.stripe_repository.get_subscription(
                        subscription.stripe_subscription_id
                    )
            else:
                logger.warning(
                    f"Could not fetch subscription {subscription_id} from Stripe"
                )
                return {
                    "status": "error",
                    "message": "Subscription not found in Stripe",
                }
        if stripe_subscription:
            await self._update_subscription_record(stripe_subscription, db_session)

        if payment_intent_id or invoice_id:
            await self._update_payment_record(
                subscription_id=subscription_id,
                payment_intent_id=payment_intent_id,
                invoice_id=invoice_id,
                standalone=standalone,
                event_type=event_type,
                event_data=event_data,
                db_session=db_session,
            )

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _update_subscription_record(
        self, stripe_subscription: Dict[str, Any], db_session: AsyncSession
    ) -> Subscription:
        """
        Update or create a subscription record based on Stripe data.
        """
        subscription_id: str = str(stripe_subscription.get("id"))

        stmt = select(Subscription).where(
            Subscription.stripe_subscription_id == subscription_id
        )
        result = await db_session.execute(stmt)
        subscription = result.scalars().first()

        if subscription is None:
            subscription = Subscription()
            subscription.stripe_subscription_id = subscription_id

        subscription.status = SubscriptionStatus(stripe_subscription.get("status"))

        current_period_start = stripe_subscription.get("current_period_start")
        if current_period_start is not None:
            subscription.current_period_start = datetime.fromtimestamp(
                float(str(current_period_start))
            )

        current_period_end = stripe_subscription.get("current_period_end")
        if current_period_end is not None:
            subscription.current_period_end = datetime.fromtimestamp(
                float(str(current_period_end))
            )

        subscription.cancel_at_period_end = stripe_subscription.get(
            "cancel_at_period_end", False
        )

        canceled_at = stripe_subscription.get("canceled_at")
        if canceled_at is not None:
            subscription.canceled_at = datetime.fromtimestamp(float(str(canceled_at)))

        ended_at = stripe_subscription.get("ended_at")
        if ended_at is not None:
            subscription.ended_at = datetime.fromtimestamp(float(str(ended_at)))

        billing_cycle_anchor = stripe_subscription.get("billing_cycle_anchor")
        if billing_cycle_anchor is not None:
            subscription.billing_cycle_anchor = datetime.fromtimestamp(
                float(str(billing_cycle_anchor))
            )

        latest_invoice = stripe_subscription.get("latest_invoice")
        if latest_invoice is not None:
            if isinstance(latest_invoice, dict):
                subscription.latest_invoice = latest_invoice.get("id")
            else:
                subscription.latest_invoice = latest_invoice

        default_payment_method = stripe_subscription.get("default_payment_method")
        if default_payment_method is not None:
            if isinstance(default_payment_method, dict):
                subscription.default_payment_method = default_payment_method.get("id")
            else:
                subscription.default_payment_method = default_payment_method

        items_data = stripe_subscription.get("items", {}).get("data")
        if items_data:
            item = items_data[0]
            price = item.get("price", {})

            subscription.stripe_price_id = price.get("id")
            subscription.amount = price.get("unit_amount", 0)
            subscription.currency = price.get("currency", "usd")

            recurring = price.get("recurring")
            if recurring:
                subscription.interval = recurring.get("interval", "month")

        db_session.add(subscription)
        await db_session.commit()
        await db_session.refresh(subscription)

        return subscription

    async def _update_payment_record(
        self,
        subscription_id: str,
        payment_intent_id: Optional[str],
        invoice_id: Optional[str],
        standalone: Optional[str],
        event_type: str,
        event_data: Dict[str, Any],
        db_session: AsyncSession,
    ) -> Optional[SubscriptionPayment]:
        """
        update or create a payment record based on event data.
        """
        stmt = select(Subscription).where(
            Subscription.stripe_subscription_id == subscription_id
        )
        result = await db_session.execute(stmt)
        subscription = result.scalars().first()

        if subscription is None:
            logger.warning(f"No subscription record found for {subscription_id}")
            return None

        payment = None
        if payment_intent_id:
            payment_stmt = select(SubscriptionPayment).where(
                SubscriptionPayment.stripe_payment_intent_id == payment_intent_id
            )
            payment_result = await db_session.execute(payment_stmt)
            payment = payment_result.scalars().first()

        if payment is None and invoice_id:
            invoice_stmt = select(SubscriptionPayment).where(
                SubscriptionPayment.stripe_invoice_id == invoice_id
            )
            invoice_result = await db_session.execute(invoice_stmt)
            payment = invoice_result.scalars().first()

        if payment is None:
            payment = SubscriptionPayment()
            payment.subscription_id = subscription.id

        if payment_intent_id:
            payment.stripe_payment_intent_id = payment_intent_id

        if invoice_id:
            payment.stripe_invoice_id = invoice_id

        # Set standalone flag based on metadata
        metadata = event_data.get("metadata", {})
        if not metadata and "payment_intent" in event_data:
            # Try to get metadata from payment intent if not in event data
            try:
                payment_intent = await self.stripe_repository.get_payment_intent(
                    event_data["payment_intent"]
                )
                if payment_intent:
                    metadata = payment_intent.get("metadata", {})
            except Exception as e:
                logger.warning(f"Failed to fetch payment intent metadata: {str(e)}")

        payment.standalone = metadata.get("standalone") == "true"

        payment_method = None
        if "payment_method" in event_data:
            payment_method = event_data["payment_method"]
        elif "payment_intent" in event_data:
            try:
                payment_intent = await self.stripe_repository.get_payment_intent(
                    event_data["payment_intent"]
                )
                if payment_intent and "payment_method" in payment_intent:
                    payment_method = await self.stripe_repository.get_payment_method(
                        payment_intent["payment_method"]
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch payment method details: {str(e)}")

        # Update card details if payment method is available
        if payment_method and "card" in payment_method:
            card = payment_method["card"]
            payment.card_brand = card.get("brand", "unknown")
            payment.card_last4 = card.get("last4", "0000")
            payment.card_exp_month = card.get("exp_month", 1)
            payment.card_exp_year = card.get("exp_year", 2000)
            payment.cardholder_name = payment_method.get("billing_details", {}).get(
                "name", ""
            )
            payment.cardholder_email = payment_method.get("billing_details", {}).get(
                "email", ""
            )

        if "succeeded" in event_type or "paid" in event_type:
            payment.status = PaymentStatus.SUCCEEDED
        elif "failed" in event_type:
            payment.status = PaymentStatus.FAILED
        elif "pending" in event_type:
            payment.status = PaymentStatus.PENDING

        if "charge" in event_type:
            charge_id = event_data.get("id")
            if charge_id is not None:
                payment.stripe_charge_id = str(charge_id)

        amount_paid = event_data.get("amount_paid")
        if amount_paid is not None:
            payment.amount_paid = int(str(amount_paid))
        elif event_data.get("amount") is not None:
            amount = event_data.get("amount")
            if amount is not None:
                payment.amount_paid = int(str(amount))
        else:
            payment.amount_paid = subscription.amount

        payment.currency = event_data.get("currency", subscription.currency)

        payment.period_start = subscription.current_period_start
        payment.period_end = subscription.current_period_end

        if "succeeded" in event_type or "paid" in event_type:
            payment.payment_date = datetime.now()

        if event_data.get("receipt_url"):
            payment.receipt_url = event_data.get("receipt_url")

        if event_data.get("invoice_pdf"):
            payment.invoice_pdf = event_data.get("invoice_pdf")

        if invoice_id and not payment.invoice_pdf:
            invoice = await self.stripe_repository.get_invoice(invoice_id)
            if invoice:
                payment.invoice_pdf = invoice.get("invoice_pdf")

                charge = invoice.get("charge")
                if charge:
                    payment.stripe_charge_id = str(charge)

        if event_data:
            payment.stripe_metadata = {
                "event_type": event_type,
                "event_data": str(event_data)[:1000],  # Truncate to avoid huge JSON
            }

        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        return payment
