from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, cast
from uuid import UUID

import stripe
from loguru import logger
from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import virtual_labs.external.accounting as accounting_service
from virtual_labs.domain.billing import TaxBehavior, TaxStatus
from virtual_labs.infrastructure.db.models import (
    BillingQuote,
    PaidSubscription,
    PaymentStatus,
    SubscriptionPayment,
    SubscriptionStatus,
    SubscriptionTierEnum,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe import helpers
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.infrastructure.stripe.helpers import DEFAULT_CURRENCY
from virtual_labs.infrastructure.stripe.mapping import (
    SubscriptionMappingError,
    apply_subscription_fields,
    map_stripe_subscription_to_db,
)
from virtual_labs.infrastructure.stripe.types import (
    InvoiceAmounts,
    PaymentIntentAmounts,
    PostCommitActions,
)
from virtual_labs.repositories.labs import get_user_virtual_lab
from virtual_labs.repositories.stripe_repo import StripeRepository
from virtual_labs.repositories.stripe_user_repo import StripeUserQueryRepository
from virtual_labs.repositories.subscription_repo import SubscriptionRepository
from virtual_labs.repositories.user_repo import UserMutationRepository
from virtual_labs.services.credit_converter import CreditConverter
from virtual_labs.utils.subscription_type_resolver import resolve_tier

# TTL for webhook idempotency keys (3 days covers Stripe's retry window)
_WEBHOOK_IDEMPOTENCY_TTL_SECONDS: int = 259_200

# stripe expand params shared by every subscription / payment-intent retrieval
_SUBSCRIPTION_EXPAND: list[str] = [
    "default_payment_method",
    "latest_invoice",
    "items.data.price",
]
_PAYMENT_INTENT_EXPAND: list[str] = [
    "payment_method",
    "latest_charge",
    "invoice",
]

EventHandler = Callable[[stripe.Event, AsyncSession], Awaitable[dict[str, Any]]]


class StripeWebhook:
    """Process Stripe webhook events with typed extraction and per-event atomicity.

    Each event handler runs inside a single DB transaction. External side
    effects (Keycloak, accounting) are queued and executed only after the
    transaction commits successfully.
    """

    subscription_update_events = helpers.SUBSCRIPTION_UPDATE_EVENTS
    subscription_upsert_events = helpers.SUBSCRIPTION_UPSERT_EVENTS
    subscription_deleted_events = helpers.SUBSCRIPTION_DELETED_EVENTS
    payment_update_events = helpers.INVOICE_PAYMENT_EVENTS
    standalone_payment_events = helpers.STANDALONE_PAYMENT_EVENTS

    def __init__(
        self,
        stripe_repository: StripeRepository,
        subscription_repository: SubscriptionRepository,
        stripe_user_repository: StripeUserQueryRepository,
        credit_converter: CreditConverter,
        redis: Redis,
    ):
        self.stripe_repository = stripe_repository
        self.subscription_repository = subscription_repository
        self.stripe_user_repository = stripe_user_repository
        self.credit_converter = credit_converter
        self.redis = redis
        self.kc_user = UserMutationRepository()

        self._handlers: dict[str, EventHandler] = {
            **{
                e: self._handle_subscription_upsert_event
                for e in self.subscription_upsert_events
            },
            **{
                e: self._handle_subscription_deleted_event
                for e in self.subscription_deleted_events
            },
            **{
                e: self._handle_invoice_payment_event
                for e in self.payment_update_events
            },
        }

    # Entry point

    async def handle_webhook_event(
        self,
        event_json: stripe.Event,
        db_session: AsyncSession,
    ) -> dict[str, Any]:
        try:
            event_type = event_json.type
            event_id = event_json.id

            if not await self._claim_idempotency(event_id):
                logger.info(
                    f"Skipping duplicate webhook event: {event_type} (ID: {event_id})"
                )
                return {
                    "status": "duplicate",
                    "event_type": event_type,
                    "event_id": event_id,
                }

            logger.info(
                f"Processing Stripe webhook event: {event_type} (ID: {event_id})"
            )

            if (
                event_type in self.standalone_payment_events
                and helpers.is_standalone_event(event_json)
            ):
                return await self._handle_standalone_payment_event(
                    event_json, db_session
                )

            handler = self._handlers.get(event_type)
            if handler is None:
                logger.info(f"Ignoring unhandled event type: {event_type}")
                return {"status": "ignored", "event_type": event_type}

            return await handler(event_json, db_session)

        except Exception as e:
            logger.exception(f"Error processing webhook event: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
            }

    async def _claim_idempotency(self, event_id: str | None) -> bool:
        """Set-NX the event id; True if claim succeeded (this is a fresh event)."""
        if not event_id:
            return True
        idempotency_key = f"stripe:webhook:processed:{event_id}"
        is_new = await self.redis.set(
            idempotency_key,
            "1",
            ex=_WEBHOOK_IDEMPOTENCY_TTL_SECONDS,
            nx=True,
        )
        return bool(is_new)

    # Subscription events
    async def _handle_subscription_upsert_event(
        self,
        event_json: stripe.Event,
        db_session: AsyncSession,
    ) -> dict[str, Any]:
        """Created / updated / pending_update_applied / pending_update_expired.

        Resource-first: pull the id from the event, fetch the live
        Subscription from Stripe (events can race), then map → DB.
        """
        event_type = event_json.type
        event_obj = cast(stripe.Subscription, event_json.data.object)
        subscription_id = helpers.resource_id_from_event(event_json)
        user_id_from_metadata = helpers.get_metadata(event_obj).get("user_id")
        if not subscription_id:
            logger.warning(f"No subscription ID found in event: {event_type}")
            return {"status": "error", "message": "No subscription ID in event"}

        # Fetch *before* opening the DB transaction so the connection
        # isn't held across a Stripe round-trip.
        stripe_subscription = await self._fetch_subscription(subscription_id)
        if stripe_subscription is None:
            return {"status": "error", "message": "Subscription not found in Stripe"}

        deferred = PostCommitActions()
        async with db_session.begin():
            staged = await self._stage_subscription_upsert(
                stripe_subscription=stripe_subscription,
                event_obj=event_obj,
                user_id_from_metadata=user_id_from_metadata,
                db_session=db_session,
                deferred=deferred,
            )
        if staged is None:
            return {
                "status": "error",
                "event_type": event_type,
                "subscription_id": subscription_id,
                "message": "Subscription not staged (missing user_id)",
            }
        await deferred.run()

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _handle_subscription_deleted_event(
        self,
        event_json: stripe.Event,
        db_session: AsyncSession,
    ) -> dict[str, Any]:
        """customer.subscription.deleted — terminal state only.

        Skips period mapping, tier flips, and pricing rewrites; just
        stamps termination fields and queues the FREE downgrade side
        effects.
        """
        event_type = event_json.type
        event_obj = cast(stripe.Subscription, event_json.data.object)
        subscription_id = helpers.resource_id_from_event(event_json)
        if not subscription_id:
            logger.warning(f"No subscription ID found in event: {event_type}")
            return {"status": "error", "message": "No subscription ID in event"}

        stripe_subscription = await self._fetch_subscription(subscription_id)
        # Stripe may already have purged a deleted subscription; fall back
        # to the inlined event payload for terminal stamping.
        live = stripe_subscription if stripe_subscription is not None else event_obj
        deferred = PostCommitActions()
        async with db_session.begin():
            subscription = await self._find_local_subscription(
                db_session, subscription_id, user_id=None
            )
            if subscription is None:
                logger.info(
                    f"No local subscription record found for {subscription_id} on delete"
                )
                return {
                    "status": "success",
                    "event_type": event_type,
                    "subscription_id": subscription_id,
                    "message": "No local record to terminate",
                }

            subscription.stripe_event = _to_dict(event_obj)
            subscription.status = SubscriptionStatus(live.status)
            subscription.cancel_at_period_end = bool(live.cancel_at_period_end)
            ended_at = helpers.get_ended_at(live) or datetime.now()
            subscription.ended_at = ended_at
            canceled_at = helpers.get_canceled_at(live)
            if canceled_at is not None:
                subscription.canceled_at = canceled_at

            self._queue_subscription_keycloak_and_tier(
                deferred, subscription, is_terminal=True
            )
            db_session.add(subscription)

        await deferred.run()

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _stage_subscription_upsert(
        self,
        stripe_subscription: stripe.Subscription,
        event_obj: stripe.Subscription,
        user_id_from_metadata: str | None,
        db_session: AsyncSession,
        deferred: PostCommitActions,
    ) -> PaidSubscription | None:
        """Single staging path for create / update / pending_* events.

        Builds the DB payload via the pure `map_stripe_subscription_to_db`
        and copies it onto the row via `apply_subscription_fields`. All
        side-effect queueing happens here in the orchestrator — never in
        the mapping function.
        """
        user_id_str = await self._resolve_user_id(
            stripe_subscription, user_id_from_metadata
        )
        if not user_id_str:
            logger.warning(
                f"Cannot stage subscription record for {stripe_subscription.id}: "
                f"missing user_id"
            )
            return None
        user_id = UUID(user_id_str)

        subscription_tier = await self._resolve_subscription_tier(
            helpers.get_product_id_from_subscription(stripe_subscription)
        )

        try:
            # The webhook is still inside its open DB transaction here
            # so reading these attributes is safe; we still pass them as
            # primitives because `map_stripe_subscription_to_db` no
            # longer accepts the ORM object (the create-subscription
            # flow can't safely hold one across its commit boundary).
            mapped = map_stripe_subscription_to_db(
                stripe_subscription,
                tier_id=UUID(str(subscription_tier.id)),
                tier_kind=subscription_tier.tier,
                user_id=user_id,
            )
        except SubscriptionMappingError as exc:
            raise ValueError(str(exc)) from exc

        subscription = await self._find_local_subscription(
            db_session, mapped.stripe_subscription_id, user_id_str
        )
        if subscription is None:
            subscription = PaidSubscription()

        subscription.stripe_event = _to_dict(event_obj)
        apply_subscription_fields(subscription, mapped)
        await self._ensure_virtual_lab_id(db_session, subscription)

        # Schedule Keycloak/tier sync. ACTIVE → upgrade, anything else
        # (past_due, unpaid, …) → terminal-style downgrade. Matches the
        # legacy `status != ACTIVE` branch that lived in the old staging
        # function.
        is_terminal = subscription.status != SubscriptionStatus.ACTIVE
        self._queue_subscription_keycloak_and_tier(
            deferred, subscription, is_terminal=is_terminal
        )

        db_session.add(subscription)
        return subscription

    # Subscription helpers
    async def _find_local_subscription(
        self,
        db_session: AsyncSession,
        stripe_subscription_id: str,
        user_id: str | None,
    ) -> PaidSubscription | None:
        stmt = select(PaidSubscription).where(
            PaidSubscription.stripe_subscription_id == stripe_subscription_id
        )
        if user_id:
            stmt = stmt.where(or_(PaidSubscription.user_id == UUID(user_id)))
        result = await db_session.execute(stmt)
        return result.scalars().first()

    async def _resolve_user_id(
        self,
        stripe_subscription: stripe.Subscription,
        provided_user_id: str | None,
    ) -> str | None:
        if provided_user_id:
            return provided_user_id
        metadata_user = helpers.get_metadata(stripe_subscription).get("user_id")
        if metadata_user:
            return metadata_user
        customer_id = helpers.get_customer_id(stripe_subscription)
        if not customer_id:
            return None
        stripe_user = await self.stripe_user_repository.get_by_stripe_customer_id(
            customer_id
        )
        return str(stripe_user.user_id) if stripe_user else None

    async def _ensure_virtual_lab_id(
        self,
        db_session: AsyncSession,
        subscription: PaidSubscription,
    ) -> None:
        if subscription.virtual_lab_id:
            return
        virtual_lab = await get_user_virtual_lab(
            db_session, UUID(str(subscription.user_id))
        )
        if virtual_lab is not None:
            subscription.virtual_lab_id = UUID(str(virtual_lab.id))

    async def _resolve_subscription_tier(self, product_id: str | None) -> Any:
        """Pick a SubscriptionTier by Stripe product id, falling back to PRO."""
        tier = (
            await self.subscription_repository.get_subscription_tier_by_product_id(
                product_id=product_id
            )
            if product_id is not None
            else None
        )
        if tier is None:
            tier = await self.subscription_repository.get_subscription_tier_by_tier(
                tier=SubscriptionTierEnum.PRO
            )
        assert tier is not None
        return tier

    def _queue_subscription_keycloak_and_tier(
        self,
        deferred: PostCommitActions,
        subscription: PaidSubscription,
        *,
        is_terminal: bool,
    ) -> None:
        user_id = subscription.user_id
        tier_label: SubscriptionTierEnum | None = (
            SubscriptionTierEnum.FREE
            if is_terminal
            else resolve_tier(subscription.subscription_type)
        )
        db_action: Callable[..., Awaitable[Any]] = (
            self.subscription_repository.downgrade_to_free
            if is_terminal
            else self.subscription_repository.deactivate_free_subscription
        )

        deferred.add(
            _wrap(
                self.kc_user.update_user_custom_properties,
                user_id=user_id,
                properties=[("plan", tier_label, "multiple")],
                log_label="Failed to update user custom properties in Keycloak",
            )
        )
        deferred.add(_wrap(db_action, user_id=user_id))

    # Invoice payment events
    async def _handle_invoice_payment_event(
        self,
        event_json: stripe.Event,
        db_session: AsyncSession,
    ) -> dict[str, Any]:
        """invoice.payment_succeeded / invoice.payment_failed.

        Resource-first: read the id from the event, fetch the live
        Invoice (and the related Subscription / PaymentIntent) from
        Stripe *before* opening the DB transaction, then map → DB. The
        inlined `event.data.object` is used only for `id`, metadata, and
        the audit JSON snapshot — never for amounts, period, address, or
        any other field that drives DB state.
        """
        event_type = event_json.type
        event_obj = cast(stripe.Invoice, event_json.data.object)

        invoice_id = helpers.resource_id_from_event(event_json)
        if not invoice_id:
            logger.warning(f"No invoice ID found in event: {event_type}")
            return {"status": "error", "message": "No invoice ID in event"}

        # Fetch the authoritative invoice. If Stripe is unreachable we
        # fall back to the event payload — better to record a stale row
        # than to drop the event entirely.
        invoice = await self._fetch_invoice(invoice_id) or event_obj

        subscription_id = helpers.get_subscription_id_from_invoice(invoice)
        payment_intent_id = helpers.get_payment_intent_id_from_invoice(invoice)
        user_id = helpers.get_invoice_user_id(invoice) or helpers.get_invoice_user_id(
            event_obj
        )

        stripe_subscription = (
            await self._fetch_subscription(subscription_id) if subscription_id else None
        )
        payment_intent = (
            await self._fetch_payment_intent(payment_intent_id)
            if payment_intent_id
            else None
        )
        customer_id = helpers.get_customer_id(invoice)
        customer = (
            await self._fetch_customer(customer_id)
            if customer_id and helpers.get_invoice_customer_address(invoice) is None
            else None
        )

        deferred = PostCommitActions()
        async with db_session.begin():
            if stripe_subscription is not None:
                await self._stage_subscription_upsert(
                    stripe_subscription=stripe_subscription,
                    event_obj=stripe_subscription,
                    user_id_from_metadata=user_id,
                    db_session=db_session,
                    deferred=deferred,
                )

            await self._stage_invoice_payment_record(
                event_obj=event_obj,
                invoice=invoice,
                payment_intent=payment_intent,
                customer=customer,
                subscription_id=subscription_id,
                payment_intent_id=payment_intent_id,
                invoice_id=invoice_id,
                event_type=event_type,
                db_session=db_session,
                deferred=deferred,
            )

        await deferred.run()

        return {
            "status": "success",
            "event_type": event_type,
            "subscription_id": subscription_id,
        }

    async def _stage_invoice_payment_record(
        self,
        event_obj: stripe.Invoice,
        invoice: stripe.Invoice,
        payment_intent: stripe.PaymentIntent | None,
        customer: stripe.Customer | None,
        subscription_id: str | None,
        payment_intent_id: str | None,
        invoice_id: str,
        event_type: str,
        db_session: AsyncSession,
        deferred: PostCommitActions,
    ) -> SubscriptionPayment:
        """Stage the SubscriptionPayment row from the fetched invoice.

        Caller hands in the freshly-fetched `invoice`, `payment_intent`,
        and (optionally) `customer` — all Stripe round-trips have
        already happened outside the transaction. `event_obj` is kept
        only for metadata merging and the audit JSON.
        """
        # Phase 1: locate or create the local payment row
        payment = await self._find_or_create_invoice_payment(
            db_session, event_obj, invoice_id
        )
        customer_id = helpers.get_customer_id(invoice)

        # Phase 2: enrich from the fetched invoice + payment intent
        metadata = helpers.merge_invoice_metadata(event_obj, invoice)
        self._apply_invoice_enrichment(
            payment, invoice, payment_intent, payment_intent_id, invoice_id
        )

        # Phase 3: link to the local PaidSubscription (autoflush is off)
        await self._link_payment_to_local_subscription(
            db_session, payment, subscription_id
        )

        # Phase 4: status, amounts, tax, currency — all from the fetched invoice
        payment.status = helpers.payment_status_from_event_type(event_type)
        amounts = helpers.get_invoice_amounts(
            invoice, default_currency=DEFAULT_CURRENCY
        )
        self._apply_invoice_amounts(payment, amounts, invoice)
        await self._apply_invoice_tax_and_billing(payment, metadata, db_session)

        # Phase 5: customer address — fetched invoice first, then customer fetch
        self._apply_customer_address(payment, invoice, customer)

        # Phase 6: success-only side effects (accounting top-up + discount)
        if payment.status == PaymentStatus.SUCCEEDED:
            payment.payment_date = datetime.now()
            local_subscription = await self._lookup_local_subscription(
                db_session, subscription_id
            )
            await self._queue_subscription_accounting(
                deferred=deferred,
                payment=payment,
                local_subscription=local_subscription,
                tier_invoice=invoice,
                invoice_id=invoice_id,
                db_session=db_session,
            )
        else:
            await self._queue_failed_payment_downgrade(deferred, customer_id)

        db_session.add(payment)
        return payment

    # Invoice payment helpers
    async def _find_or_create_invoice_payment(
        self,
        db_session: AsyncSession,
        event_obj: stripe.Invoice,
        invoice_id: str,
    ) -> SubscriptionPayment:
        invoice_stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.stripe_invoice_id == invoice_id
        )
        invoice_result = await db_session.execute(invoice_stmt)
        existing = invoice_result.scalars().first()
        if existing is not None:
            return existing

        customer_id = helpers.get_customer_id(event_obj)
        payment = SubscriptionPayment()
        payment.stripe_invoice_id = invoice_id
        _set_if(payment, customer_id=customer_id)
        payment.stripe_event = _to_dict(event_obj)
        return payment

    @staticmethod
    def _apply_invoice_enrichment(
        payment: SubscriptionPayment,
        invoice: stripe.Invoice,
        payment_intent: stripe.PaymentIntent | None,
        event_payment_intent_id: str | None,
        invoice_id: str,
    ) -> None:
        """Period dates + payment-intent-derived card details + invoice PDF.

        `payment_intent` is fetched outside the transaction by the
        orchestrator and passed in — this helper performs no I/O.
        """
        period = helpers.get_invoice_period(invoice)
        _set_if(
            payment,
            period_start=_ts_to_datetime(period.start),
            period_end=_ts_to_datetime(period.end),
        )

        invoice_pi_id = helpers.get_payment_intent_id_from_invoice(invoice)
        effective_pi_id = event_payment_intent_id or invoice_pi_id
        if effective_pi_id:
            payment.stripe_payment_intent_id = effective_pi_id

        if payment_intent is not None:
            card = helpers.get_card_details(payment_intent)
            if card is not None:
                payment.card_brand = card.brand
                payment.card_last4 = card.last4
                payment.card_exp_month = card.exp_month
                payment.card_exp_year = card.exp_year
            else:
                logger.warning(
                    f"No payment method found in payment intent for invoice {invoice_id}"
                )

        payment.invoice_pdf = invoice.invoice_pdf

    async def _lookup_local_subscription(
        self,
        db_session: AsyncSession,
        stripe_subscription_id: str | None,
    ) -> PaidSubscription | None:
        """Read-only counterpart to `_link_payment_to_local_subscription`."""
        if not stripe_subscription_id:
            return None
        await db_session.flush()
        stmt = select(PaidSubscription).where(
            PaidSubscription.stripe_subscription_id == stripe_subscription_id
        )
        result = await db_session.execute(stmt)
        return result.scalars().first()

    async def _link_payment_to_local_subscription(
        self,
        db_session: AsyncSession,
        payment: SubscriptionPayment,
        stripe_subscription_id: str | None,
    ) -> PaidSubscription | None:
        if not stripe_subscription_id:
            return None
        # autoflush=False on this session: flush the staged subscription so the
        # SELECT below can see it.
        await db_session.flush()
        stmt = select(PaidSubscription).where(
            PaidSubscription.stripe_subscription_id == stripe_subscription_id
        )
        result = await db_session.execute(stmt)
        local_subscription = result.scalars().first()
        if local_subscription is not None:
            payment.subscription_id = local_subscription.id
        return local_subscription

    @staticmethod
    def _apply_invoice_amounts(
        payment: SubscriptionPayment,
        amounts: InvoiceAmounts,
        invoice: stripe.Invoice,
    ) -> None:
        payment.amount_paid = amounts.amount_paid
        payment.amount_subtotal = amounts.subtotal
        payment.amount_tax = amounts.tax
        payment.amount_total = amounts.total
        payment.tax_behavior = helpers.tax_behavior_from_invoice(
            invoice
        ) or TaxBehavior(settings.BILLING_TAX_BEHAVIOR)
        payment.tax_status = (
            TaxStatus.CALCULATED if amounts.tax else TaxStatus.NOT_APPLICABLE
        )
        payment.currency = amounts.currency

    async def _apply_invoice_tax_and_billing(
        self,
        payment: SubscriptionPayment,
        metadata: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        billing_quote_id = metadata.get("billing_quote_id")
        quote: BillingQuote | None = None
        if billing_quote_id:
            quote = await db_session.get(BillingQuote, UUID(str(billing_quote_id)))
            payment.billing_quote_id = UUID(str(billing_quote_id))
        if quote is not None:
            payment.billing_address_json = quote.billing_address_json
            payment.stripe_tax_calculation_id = quote.stripe_tax_calculation_id
            payment.tax_status = quote.tax_status
        elif metadata.get("stripe_tax_calculation_id"):
            payment.stripe_tax_calculation_id = str(
                metadata["stripe_tax_calculation_id"]
            )

    @staticmethod
    def _apply_customer_address(
        payment: SubscriptionPayment,
        invoice: stripe.Invoice,
        customer: stripe.Customer | None,
    ) -> None:
        """Resolve the billing address from the fetched invoice → customer.

        The inlined event payload is not consulted: invoice address is the
        authoritative copy, and the customer fetch (already done outside
        the transaction by the orchestrator) covers the case where an
        invoice was created without a snapshotted customer_address.
        """
        address = helpers.get_invoice_customer_address(invoice)
        if address is None and customer is not None:
            address = helpers.get_customer_address(customer)
        if not address:
            return
        payment.tax_country = address.get("country")
        payment.billing_address_json = payment.billing_address_json or address

    async def _queue_subscription_accounting(
        self,
        deferred: PostCommitActions,
        payment: SubscriptionPayment,
        local_subscription: PaidSubscription | None,
        tier_invoice: stripe.Invoice,
        invoice_id: str,
        db_session: AsyncSession,
    ) -> None:
        product_id = helpers.get_product_id_from_invoice(tier_invoice)
        price_id = helpers.get_price_id_from_invoice(tier_invoice)

        subscription_tier = await self._resolve_subscription_tier(product_id)

        if local_subscription is None:
            logger.warning(
                f"No local subscription record found for invoice {invoice_id}; "
                f"skipping subscription accounting updates"
            )
            return

        virtual_lab = await get_user_virtual_lab(db_session, local_subscription.user_id)
        if not accounting_service.is_enabled or virtual_lab is None:
            return

        virtual_lab_id = UUID(str(virtual_lab.id))
        credit_amount = (
            subscription_tier.yearly_credits
            if subscription_tier.stripe_yearly_price_id == price_id
            else subscription_tier.monthly_credits
        )
        period_start = local_subscription.current_period_start
        period_end = local_subscription.current_period_end

        deferred.add(
            _wrap(
                accounting_service.top_up_virtual_lab_budget,
                virtual_lab_id,
                float(credit_amount),
            )
        )
        deferred.add(
            _wrap(
                accounting_service.create_virtual_lab_discount,
                virtual_lab_id=virtual_lab_id,
                discount=settings.PAID_SUBSCRIPTION_DISCOUNT,
                valid_from=period_start.replace(tzinfo=timezone.utc),
                valid_to=period_end.replace(tzinfo=timezone.utc),
            )
        )

    async def _queue_failed_payment_downgrade(
        self,
        deferred: PostCommitActions,
        customer_id: str | None,
    ) -> None:
        if not customer_id:
            return
        user = await self.stripe_user_repository.get_by_stripe_customer_id(
            stripe_customer_id=str(customer_id)
        )
        if user is None:
            return
        deferred.add(
            _wrap(
                self.subscription_repository.downgrade_to_free,
                user_id=UUID(str(user.user_id)),
            )
        )

    # Standalone payment events

    async def _handle_standalone_payment_event(
        self,
        event_json: stripe.Event,
        db_session: AsyncSession,
    ) -> dict[str, Any]:
        """payment_intent.succeeded / payment_failed / canceled (standalone).

        Resource-first: read the id from the event, fetch the live
        PaymentIntent from Stripe (with `latest_charge` + `payment_method`
        expanded) before opening the DB transaction. Amounts, charge
        info, and card details all come from the fetched resource.
        Metadata still comes from the event because we set it at create
        time and it does not change between events.
        """
        event_type = event_json.type
        event_obj = cast(stripe.PaymentIntent, event_json.data.object)

        payment_intent_id = helpers.resource_id_from_event(event_json)
        if not payment_intent_id:
            logger.error("No payment intent ID found in event data")
            return {
                "status": "error",
                "message": "No payment intent ID in event data",
            }

        metadata = helpers.get_metadata(event_obj)
        customer_id = helpers.get_customer_id(event_obj)
        user_id = metadata.get("user_id")
        virtual_lab_id = metadata.get("virtual_lab_id")

        validation_error = self._validate_standalone_payload(
            payment_intent_id, customer_id, user_id, virtual_lab_id
        )
        if validation_error is not None:
            return validation_error

        # mypy: validated above
        assert (
            customer_id is not None
            and user_id is not None
            and virtual_lab_id is not None
        )

        # Resource fetch outside the transaction. Fall back to the event
        # payload if Stripe is unreachable so the event still records.
        payment_intent = (
            await self._fetch_payment_intent(payment_intent_id) or event_obj
        )

        try:
            deferred = PostCommitActions()
            payment_db_id: str | None = None
            async with db_session.begin():
                payment = await self._stage_standalone_payment_record(
                    event_obj=event_obj,
                    payment_intent=payment_intent,
                    payment_intent_id=payment_intent_id,
                    customer_id=customer_id,
                    user_id=user_id,
                    virtual_lab_id=virtual_lab_id,
                    event_type=event_type,
                    metadata=metadata,
                    db_session=db_session,
                    deferred=deferred,
                )
                # Capture the id while the session is still attached;
                # accessing it after the `begin()` block commits would
                # trigger an async refresh outside the greenlet context.
                if payment is not None:
                    await db_session.flush()
                    payment_db_id = str(payment.id) if payment.id else None
            await deferred.run()

            return {
                "status": "success",
                "event_type": event_type,
                "payment_id": payment_db_id,
            }
        except Exception as e:
            logger.error(f"Error processing standalone payment: {str(e)}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _validate_standalone_payload(
        payment_intent_id: str,
        customer_id: str | None,
        user_id: str | None,
        virtual_lab_id: str | None,
    ) -> dict[str, Any] | None:
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
                f"No user ID or virtual lab ID found in payment intent metadata: "
                f"{payment_intent_id}"
            )
            return {
                "status": "error",
                "field_missing": "user_id" if not user_id else "virtual_lab_id",
                "message": "No user ID or virtual lab ID in payment intent metadata",
            }
        try:
            UUID(user_id)
            UUID(virtual_lab_id)
        except ValueError as e:
            logger.error(f"Invalid UUID format for user_id: {user_id}")
            return {
                "status": "error",
                "message": f"Invalid user ID format: {str(e)}",
            }
        return None

    async def _stage_standalone_payment_record(
        self,
        event_obj: stripe.PaymentIntent,
        payment_intent: stripe.PaymentIntent,
        payment_intent_id: str,
        customer_id: str,
        user_id: str,
        virtual_lab_id: str,
        event_type: str,
        metadata: dict[str, str],
        db_session: AsyncSession,
        deferred: PostCommitActions,
    ) -> SubscriptionPayment | None:
        # idempotency on the payment intent
        payment, already_succeeded = await self._find_or_create_standalone_payment(
            db_session,
            event_obj,
            payment_intent_id,
            customer_id,
            virtual_lab_id,
            user_id,
        )
        if already_succeeded:
            return payment

        # enrich card / charge from the freshly fetched intent
        self._apply_payment_intent_enrichment(payment, payment_intent)

        # status + amounts + tax/billing — amounts read off the
        # fetched resource, not the (potentially stale) event payload.
        payment.status = helpers.payment_status_from_event_type(event_type)
        amounts = helpers.get_payment_intent_amounts(
            payment_intent,
            metadata,
            default_currency=DEFAULT_CURRENCY,
        )
        await self._apply_standalone_amounts_and_tax(
            payment, amounts, metadata, db_session
        )

        payment.payment_date = datetime.now()

        # success-only credit conversion + accounting top-up
        if payment.status == PaymentStatus.SUCCEEDED:
            credits = await self.credit_converter.currency_to_credits(
                amounts.subtotal, payment.currency
            )
            payment.credits_purchased = int(credits)
            # commit the tax calculation as a Stripe Tax Transaction so the
            # tax shows up in the dashboard. Subscriptions get this for free
            # via `automatic_tax`; standalone PaymentIntents must commit
            # explicitly.
            # Deferred so it runs only after the local DB
            # transaction commits, keeps Stripe and our DB in sync
            calculation_id = payment.stripe_tax_calculation_id
            if calculation_id:
                deferred.add(
                    _wrap(
                        self.stripe_repository.commit_tax_transaction,
                        calculation_id=str(calculation_id),
                        reference=payment_intent_id,
                        log_label=(
                            f"Failed to commit standalone tax transaction "
                            f"for {payment_intent_id}"
                        ),
                    )
                )
            if accounting_service.is_enabled:
                deferred.add(
                    _wrap(
                        accounting_service.top_up_virtual_lab_budget,
                        UUID(virtual_lab_id),
                        float(credits),
                    )
                )

        # standalone bookkeeping fields
        payment.standalone = True
        now = datetime.now()
        payment.period_start = now
        payment.period_end = now

        logger.info(f"Creating/updating standalone payment record: {payment_intent_id}")
        logger.info(f"Payment status: {payment.status}")
        logger.info(f"Amount: {payment.amount_paid} {payment.currency}")

        db_session.add(payment)
        return payment

    # standalone payment helpers
    async def _find_or_create_standalone_payment(
        self,
        db_session: AsyncSession,
        event_obj: stripe.PaymentIntent,
        payment_intent_id: str,
        customer_id: str,
        virtual_lab_id: str,
        user_id: str,
    ) -> tuple[SubscriptionPayment, bool]:
        """Return (payment, already_succeeded). When already succeeded, caller exits early."""
        stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.stripe_payment_intent_id == payment_intent_id
        )
        result = await db_session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None and existing.status == PaymentStatus.SUCCEEDED:
            logger.info(f"Standalone payment {payment_intent_id} was already processed")
            return existing, True

        active_subscription = (
            await self.subscription_repository.get_active_subscription_by_user_id(
                UUID(user_id)
            )
        )
        if active_subscription is None:
            logger.info(f"No active subscription found in database for user: {user_id}")

        if existing is not None:
            return existing, False

        payment = SubscriptionPayment()
        payment.stripe_payment_intent_id = payment_intent_id
        payment.customer_id = customer_id
        payment.virtual_lab_id = UUID(virtual_lab_id)
        payment.stripe_event = _to_dict(event_obj)
        if active_subscription is not None:
            payment.subscription_id = active_subscription.id
        return payment, False

    @staticmethod
    def _apply_payment_intent_enrichment(
        payment: SubscriptionPayment,
        payment_intent: stripe.PaymentIntent,
    ) -> None:
        charge = helpers.get_charge_info(payment_intent)
        if charge is not None:
            payment.stripe_charge_id = charge.charge_id
            payment.receipt_url = charge.receipt_url

        # `card_*` columns are NOT NULL on `subscription_payment`. A
        # PaymentIntent that fails before the card is captured (Radar
        # block, declined card, abandoned 3DS, etc.) may carry no PM
        # info on the PI itself; `get_card_details` already falls back
        # to `last_payment_error.payment_method`, but if even that is
        # missing we still need to satisfy the schema. Default to the
        # same placeholders `get_card_details` uses when card fields
        # are present but empty.
        card = helpers.get_card_details(payment_intent)
        if card is None:
            payment.card_brand = payment.card_brand or "unknown"
            payment.card_last4 = payment.card_last4 or "0000"
            payment.card_exp_month = payment.card_exp_month or 1
            payment.card_exp_year = payment.card_exp_year or 2000
            return
        payment.card_brand = card.brand
        payment.card_last4 = card.last4
        payment.card_exp_month = card.exp_month
        payment.card_exp_year = card.exp_year

    async def _apply_standalone_amounts_and_tax(
        self,
        payment: SubscriptionPayment,
        amounts: PaymentIntentAmounts,
        metadata: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        payment.amount_paid = amounts.total
        payment.amount_subtotal = amounts.subtotal
        payment.amount_tax = amounts.tax
        payment.amount_total = amounts.total
        payment.tax_behavior = helpers.tax_behavior_from_metadata(metadata)
        payment.tax_country = metadata.get("tax_country") or None
        payment.tax_status = helpers.tax_status_from_metadata(metadata)
        # stripe's Payment Intents + Tax integration stores the calculation
        # id under `metadata.tax_calculation` on the PaymentIntent itself
        # read it straight from the event payload rather than relying on the
        # caller-supplied `stripe_tax_calculation_id` mirror.
        payment.stripe_tax_calculation_id = (
            metadata.get("tax_calculation")
            or metadata.get("stripe_tax_calculation_id")
            or None
        )
        payment.credit_base_amount = amounts.subtotal
        payment.currency = amounts.currency

        billing_quote_id = metadata.get("billing_quote_id")
        if not billing_quote_id:
            return
        quote = await db_session.get(BillingQuote, UUID(str(billing_quote_id)))
        payment.billing_quote_id = UUID(str(billing_quote_id))
        if quote is None:
            return
        payment.billing_address_json = quote.billing_address_json
        payment.stripe_tax_calculation_id = (
            quote.stripe_tax_calculation_id or payment.stripe_tax_calculation_id
        )

    # Stripe API helpers
    async def _fetch_subscription(
        self, subscription_id: str
    ) -> stripe.Subscription | None:
        try:
            return await stripe_client.subscriptions.retrieve_async(
                subscription_id, params={"expand": _SUBSCRIPTION_EXPAND}
            )
        except stripe.StripeError as e:
            logger.exception(
                f"Error retrieving subscription {subscription_id}: {str(e)}"
            )
            return None

    async def _fetch_invoice(self, invoice_id: str) -> stripe.Invoice | None:
        try:
            return await stripe_client.invoices.retrieve_async(invoice_id)
        except stripe.StripeError as e:
            logger.warning(f"Failed to fetch invoice {invoice_id}: {str(e)}")
            return None

    async def _fetch_payment_intent(
        self, payment_intent_id: str
    ) -> stripe.PaymentIntent | None:
        try:
            return await stripe_client.payment_intents.retrieve_async(
                payment_intent_id, params={"expand": _PAYMENT_INTENT_EXPAND}
            )
        except stripe.StripeError as e:
            logger.warning(
                f"Error retrieving payment intent {payment_intent_id}: {str(e)}"
            )
            return None

    async def _fetch_customer(self, customer_id: str) -> stripe.Customer | None:
        try:
            return await stripe_client.customers.retrieve_async(str(customer_id))
        except stripe.StripeError as e:
            logger.warning(f"Failed to fetch customer {customer_id}: {str(e)}")
            return None


# Module-level helpers
def _set_if(target: object, **fields: Any) -> None:
    """Assign each kwarg to `target` only when its value is not None.

    Replaces the verbose `if x is not None: target.x = x` boilerplate. Use
    this for fields where missing data should preserve the existing local
    value (legacy null-skip semantics).
    """
    for name, value in fields.items():
        if value is not None:
            setattr(target, name, value)


def _ts_to_datetime(ts: int | None) -> datetime | None:
    """Naive local datetime from a Unix timestamp; matches legacy semantics."""
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts))


def _to_dict(obj: object) -> dict[str, Any]:
    """Recursively materialize a StripeObject into a plain dict.

    Used to capture the original event payload in the `stripe_event` JSON
    column. `StripeObject` extends `dict`, so we walk the structure and
    coerce nested `dict` / list values without relying on the deprecated
    `to_dict_recursive` private API.
    """
    return cast(dict[str, Any], _to_jsonable(obj)) if isinstance(obj, dict) else {}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    return value


def _wrap(
    fn: Callable[..., Awaitable[Any]],
    *args: Any,
    log_label: str | None = None,
    **kwargs: Any,
) -> Callable[[], Awaitable[None]]:
    """Bind a coroutine function with args for deferred post-commit execution."""

    async def runner() -> None:
        try:
            await fn(*args, **kwargs)
        except Exception as exc:
            label = (
                log_label
                or f"Post-commit action {getattr(fn, '__name__', '<callable>')} failed"
            )
            logger.warning(f"{label}: {exc}")

    return runner
