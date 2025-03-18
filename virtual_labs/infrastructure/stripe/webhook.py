from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import stripe
from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    PaymentStatus,
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionType,
)
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.stripe_user_repo import StripeUserQueryRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository


class StripeWebhook:
    """
    module for handling Stripe webhook events and updating database records.
    """

    subscription_update_events = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.pending_update_applied",
        "customer.subscription.pending_update_expired",
    }

    payment_update_events = {
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }

    standalone_payment_events = {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
    }

    def __init__(
        self,
        stripe_repository: StripeRepository,
        subscription_repository: SubscriptionRepository,
        stripe_user_repository: StripeUserQueryRepository,
    ):
        self.stripe_repository = stripe_repository
        self.subscription_repository = subscription_repository
        self.stripe_user_repository = stripe_user_repository

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

            metadata = event_json.get("data", {}).get("object", {}).get("metadata", {})

            if event_type in self.subscription_update_events:
                return await self._handle_subscription_event(event_json, db_session)
            if metadata.get("standalone") and (
                event_type in self.standalone_payment_events
            ):
                return await self._handle_standalone_payment_event(
                    event_json, db_session
                )
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

    async def _handle_standalone_payment_event(
        self, event_json: Dict[str, Any], db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handle standalone payment intent events.
        these are payments that the user make at anytime during the subscription
        """
        event_type: str = str(event_json.get("type"))
        event_data: Dict[str, Any] = event_json.get("data", {}).get("object", {})

        payment_intent_id = event_data.get("id")
        if not payment_intent_id:
            logger.error("No payment intent ID found in event data")
            return {
                "status": "error",
                "message": "No payment intent ID in event data",
            }

        metadata = event_data.get("metadata", {})
        customer_id = event_data.get("customer")
        user_id = metadata.get("user_id")
        virtual_lab_id = metadata.get("virtual_lab_id")

        if not customer_id:
            logger.warning(
                f"No customer ID found in payment intent: {payment_intent_id}"
            )
            return {
                "status": "error",
                "field_missing": "customer_id",
                "message": "No customer ID in payment intent",
            }

        if not user_id or not virtual_lab_id:
            logger.warning(
                f"No user ID or virtual lab ID found in payment intent metadata: {payment_intent_id}"
            )
            return {
                "status": "error",
                "field_missing": "user_id" if not user_id else "virtual_lab_id",
                "message": "No user ID or virtual lab ID in payment intent metadata",
            }

        try:
            # Create or update standalone payment record
            payment = await self._create_standalone_payment_record(
                payment_intent_id=payment_intent_id,
                user_id=user_id,
                virtual_lab_id=virtual_lab_id,
                event_type=event_type,
                event_data=event_data,
                db_session=db_session,
            )

            return {
                "status": "success",
                "event_type": event_type,
                "payment_id": str(payment.id) if payment else None,
            }

        except ValueError as e:
            logger.error(f"Invalid UUID format for user_id: {user_id}")
            return {
                "status": "error",
                "message": f"Invalid user ID format: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Error processing standalone payment: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
            }

    async def _create_standalone_payment_record(
        self,
        payment_intent_id: Optional[str],
        user_id: str,
        virtual_lab_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        db_session: AsyncSession,
    ) -> Optional[SubscriptionPayment]:
        """
        create or update a standalone payment record based on payment intent data.
        this is used for one-time payments that are not tied to an invoice.
        """
        if not payment_intent_id:
            logger.error("Cannot create payment record without payment intent ID")
            return None

        stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.stripe_payment_intent_id == payment_intent_id
        )
        result = await db_session.execute(stmt)
        payment = result.scalars().first()

        customer_id = event_data.get("customer")
        subscription = None
        try:
            if subscription:
                payment.subscription_id = subscription.id
            subscription = (
                await self.subscription_repository.get_active_subscription_by_user_id(
                    UUID(user_id),
                )
            )
            if not subscription:
                logger.info(
                    f"No active subscription found in database for user: {user_id}"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch subscription from database: {str(e)}")

        if payment is None:
            payment = SubscriptionPayment()
            payment.stripe_payment_intent_id = payment_intent_id
            payment.customer_id = customer_id  # type: ignore
            payment.virtual_lab_id = UUID(virtual_lab_id)
            payment.stripe_event = event_data
            if subscription:
                payment.subscription_id = subscription.id

        try:
            payment_intent = await self.stripe_repository.get_payment_intent(
                payment_intent_id
            )
            if payment_intent:
                if latest_charge := payment_intent.get("latest_charge", {}):
                    payment.stripe_charge_id = latest_charge.get("id")
                    payment.receipt_url = latest_charge.get("receipt_url")

                if payment_method := payment_intent.get("payment_method"):
                    if payment_method and "card" in payment_method:
                        card = payment_method["card"]
                        payment.card_brand = card.get("brand", "unknown")
                        payment.card_last4 = card.get("last4", "0000")
                        payment.card_exp_month = card.get("exp_month", 1)
                        payment.card_exp_year = card.get("exp_year", 2000)

            if "succeeded" in event_type or "paid" in event_type:
                payment.status = PaymentStatus.SUCCEEDED
            elif "failed" in event_type or "canceled" in event_type:
                payment.status = PaymentStatus.FAILED
            else:
                payment.status = PaymentStatus.PENDING

            amount = event_data.get("amount", 0)
            if isinstance(amount, str):
                amount = int(amount)
            payment.amount_paid = amount
            payment.currency = event_data.get("currency", "usd")

            if payment.status == PaymentStatus.SUCCEEDED:
                # TODO: popup credits to accounting
                payment.payment_date = datetime.now()

            # mark as standalone payment
            payment.standalone = True

            # for standalone payments, use current time for period dates
            current_time = datetime.now()
            payment.period_start = current_time
            payment.period_end = current_time

            logger.info(
                f"Creating/updating standalone payment record: {payment_intent_id}"
            )
            logger.info(f"Payment status: {payment.status}")
            logger.info(f"Amount: {payment.amount_paid} {payment.currency}")

            db_session.add(payment)
            await db_session.commit()
            await db_session.refresh(payment)

            return payment

        except Exception as e:
            logger.exception(f"Failed to create standalone payment record: {str(e)}")
            raise

    async def _handle_subscription_event(
        self, event_json: Dict[str, Any], db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handle subscription related events by fetching the latest subscription data
        and updating the database.
        """
        event_type = event_json.get("type")
        subscription_id = event_json.get("data", {}).get("object", {}).get("id")
        event_data: Dict[str, Any] = event_json.get("data", {}).get("object", {})
        metadata = event_data.get("metadata", {})
        user_id = metadata.get("user_id")

        if not subscription_id:
            logger.warning(f"No subscription ID found in event: {event_type}")
            return {
                "status": "error",
                "message": "No subscription ID in event",
            }

        stripe_subscription = await self.stripe_repository.get_subscription(
            subscription_id
        )

        if not stripe_subscription:
            logger.warning(
                f"Could not fetch subscription {subscription_id} from Stripe"
            )
            return {"status": "error", "message": "Subscription not found in Stripe"}

        await self._update_subscription_record(
            stripe_subscription,
            {},
            user_id,
            str(event_type),
            db_session,
        )

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _update_subscription_record(
        self,
        stripe_subscription: Dict[str, Any],
        event_json: Dict[str, Any],
        user_id: str,
        event_type: str,
        db_session: AsyncSession,
    ) -> PaidSubscription:
        """
        Update or create a paid subscription record based on Stripe data.
        Only handles PaidSubscription since this comes from Stripe.
        """
        subscription_id: str = str(stripe_subscription.get("id"))
        stmt = select(PaidSubscription).where(
            PaidSubscription.stripe_subscription_id == subscription_id
        )
        if user_id:
            stmt = stmt.where(or_(PaidSubscription.user_id == UUID(user_id)))

        result = await db_session.execute(stmt)
        subscription = result.scalars().first()

        # Handle the case where subscription might be None
        if subscription is None:
            subscription = PaidSubscription()
            subscription.stripe_subscription_id = subscription_id
            subscription.stripe_event = event_json
        else:
            # Only update stripe_event if subscription exists
            subscription.stripe_event = (
                event_json if event_json else subscription.stripe_event
            )

        # determine subscription type based on price/product data for future
        items_data = stripe_subscription.get("items", {}).get("data", [])
        if items_data:
            item = items_data[0]
            price = item.get("price", {})
            # TODO: use product to determine PRO vs PREMIUM
            subscription.subscription_type = SubscriptionType.PRO

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

        if items_data:
            item = items_data[0]
            price = item.get("price", {})

            subscription.stripe_price_id = price.get("id")
            subscription.amount = price.get("unit_amount", 0)
            subscription.currency = price.get("currency", "chf")

            recurring = price.get("recurring")
            if recurring:
                subscription.interval = recurring.get("interval", "month")

        if (  # if the subscription is deleted or has no active status
            event_type == "customer.subscription.deleted"
            or subscription.status != "active"
        ):
            # TODO: update the user custom property "plan" to "free" in KC
            await self.subscription_repository.downgrade_to_free(
                user_id=subscription.user_id
            )
        else:  # if there is a free subscription paused it
            # TODO: update the user custom property "plan" to "paid" in KC
            await self.subscription_repository.deactivate_free_subscription(
                user_id=subscription.user_id
            )

        db_session.add(subscription)
        await db_session.commit()
        await db_session.refresh(subscription)

        return subscription

    async def _handle_payment_event(
        self, event_json: Dict[str, Any], db_session: AsyncSession
    ) -> Dict[str, Any]:
        """
        handle invoice payment events by updating payment records.
        """
        event_type: str = str(event_json.get("type"))
        event_data: Dict[str, Any] = event_json.get("data", {}).get("object", {})

        subscription_id = event_data.get("subscription")
        payment_intent_id = event_data.get("payment_intent")
        invoice_id = event_data.get("id")
        user_id = (
            event_data.get("subscription_details", {})
            .get("metadata", {})
            .get("user_id")
        )

        if not invoice_id:
            logger.warning(f"No invoice ID found in event: {event_type}")
            return {
                "status": "error",
                "message": "No invoice ID in event",
            }

        if not subscription_id:
            invoice = await self.stripe_repository.get_invoice(invoice_id)
            if invoice:
                subscription_id = invoice.get("subscription")

        stripe_subscription = None
        if subscription_id:
            stripe_subscription = await self.stripe_repository.get_subscription(
                subscription_id
            )
            if stripe_subscription:
                await self._update_subscription_record(
                    stripe_subscription,
                    {},
                    user_id,
                    event_type,
                    db_session,
                )

        await self._update_payment_record(
            subscription_id=subscription_id,
            payment_intent_id=payment_intent_id,
            invoice_id=invoice_id,
            event_type=event_type,
            event_data=event_data,
            db_session=db_session,
        )

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _update_payment_record(
        self,
        subscription_id: Optional[str],
        payment_intent_id: Optional[str],
        invoice_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        db_session: AsyncSession,
    ) -> Optional[SubscriptionPayment]:
        """
        update or create a payment record based on invoice event data.
        """

        invoice_stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.stripe_invoice_id == invoice_id
        )
        invoice_result = await db_session.execute(invoice_stmt)
        payment = invoice_result.scalars().first()
        customer_id = event_data.get("customer")

        if payment is None:
            payment = SubscriptionPayment()
            payment.stripe_invoice_id = invoice_id
            payment.customer_id = str(customer_id)
            payment.stripe_event = event_data
        # get period dates and other details from invoice
        try:
            invoice = await self.stripe_repository.get_invoice(invoice_id)
            if invoice:
                period = invoice.get("lines", {}).get("data", [{}])[0].get("period", {})
                if period:
                    start = period.get("start")
                    end = period.get("end")
                    if start:
                        payment.period_start = datetime.fromtimestamp(float(str(start)))
                    if end:
                        payment.period_end = datetime.fromtimestamp(float(str(end)))

                payment_intent = None
                if payment_intent_id:
                    payment.stripe_payment_intent_id = payment_intent_id
                    try:
                        payment_intent = (
                            await self.stripe_repository.get_payment_intent(
                                payment_intent_id
                            )
                        )

                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch payment intent details: {str(e)}"
                        )
                elif invoice.get("payment_intent"):
                    try:
                        payment_intent = (
                            await self.stripe_repository.get_payment_intent(
                                invoice["payment_intent"]
                            )
                        )
                        payment.stripe_payment_intent_id = invoice["payment_intent"]
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch payment intent details: {str(e)}"
                        )

                # get payment method from payment intent
                if payment_intent and (
                    payment_method_details := payment_intent.get("payment_method")
                ):
                    try:
                        if payment_method_details and "card" in payment_method_details:
                            card = payment_method_details["card"]
                            payment.card_brand = card.get("brand", "unknown")
                            payment.card_last4 = card.get("last4", "0000")
                            payment.card_exp_month = card.get("exp_month", 1)
                            payment.card_exp_year = card.get("exp_year", 2000)
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch payment method details: {str(e)}"
                        )
                else:
                    logger.warning(
                        f"No payment method found in payment intent for invoice {invoice_id}"
                    )

                # Get invoice PDF URL
                payment.invoice_pdf = invoice.get("invoice_pdf")

        except Exception as e:
            logger.warning(f"Failed to fetch invoice details: {str(e)}")

        # link to subscription
        if subscription_id:
            stmt = select(PaidSubscription).where(
                PaidSubscription.stripe_subscription_id == subscription_id
            )
            result = await db_session.execute(stmt)
            subscription = result.scalars().first()
            if subscription:
                payment.subscription_id = subscription.id

        # payment status based on event type
        if "succeeded" in event_type or "paid" in event_type:
            payment.status = PaymentStatus.SUCCEEDED
        elif "failed" in event_type:
            payment.status = PaymentStatus.FAILED
        else:
            payment.status = PaymentStatus.PENDING

        amount = event_data.get("amount_paid", event_data.get("amount", 0))
        payment.amount_paid = amount
        payment.currency = event_data.get("currency", "usd")

        if "succeeded" in event_type or "paid" in event_type:
            # TODO: popup credits to accounting
            payment.payment_date = datetime.now()
        else:
            user = await self.stripe_user_repository.get_by_stripe_customer_id(
                stripe_customer_id=str(customer_id)
            )
            if user:
                await self.subscription_repository.downgrade_to_free(
                    user_id=UUID(str(user.user_id)),
                )

        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        return payment
