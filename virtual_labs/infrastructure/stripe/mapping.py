"""Pure mapping from `stripe.Subscription` to local DB columns.

The function below is the single source of truth for "what fields does a
`PaidSubscription` row get from a Stripe Subscription". It performs no
I/O, touches no DB session, and is fully unit-testable against
`stripe.util.convert_to_stripe_object` fixtures.

The orchestrator in `webhook.py` calls this once per event, then copies
the resulting `SubscriptionFields` onto the row inside its DB
transaction. Side-effects (Keycloak, accounting, deferred actions) live
in the orchestrator, not here.

This is also the seam that v2 thin events will plug into: the dispatcher
will fetch the live `stripe.Subscription` from `event.related_object.id`
and hand it straight to this function — nothing inside this module
depends on the v1 inlined event payload.
"""

from __future__ import annotations

from uuid import UUID

import stripe

from virtual_labs.infrastructure.db.models import (
    PaidSubscription,
    SubscriptionStatus,
    SubscriptionTierEnum,
    SubscriptionType,
)
from virtual_labs.infrastructure.stripe import helpers
from virtual_labs.infrastructure.stripe.duration import (
    get_subscription_period_datetimes,
)
from virtual_labs.infrastructure.stripe.types import SubscriptionFields


class SubscriptionMappingError(ValueError):
    """Raised when a Stripe Subscription cannot be mapped to DB fields."""


def map_stripe_subscription_to_db(
    sub: stripe.Subscription,
    *,
    tier_id: UUID,
    tier_kind: SubscriptionTierEnum,
    user_id: UUID,
) -> SubscriptionFields:
    """Build the DB-field payload for a Stripe Subscription.

    Takes `tier_id` / `tier_kind` as primitives rather than a
    `SubscriptionTier` ORM object: the synchronous create-subscription
    flow needs to call this *after* the Phase-1 transaction has
    committed, at which point the ORM object's attributes are
    expired and would trigger a sync-context lazy load that fails
    under asyncpg with `MissingGreenlet`. Passing primitives keeps
    the mapper free of session lifetime concerns.

    Required fields raise `SubscriptionMappingError` when missing —
    the orchestrator translates that into an error response.
    Optional fields return `None` so the orchestrator can keep the
    existing local value (legacy null-skip semantics).
    """
    subscription_id = sub.id
    if not subscription_id:
        raise SubscriptionMappingError("Subscription is missing an id")

    period_start, period_end = get_subscription_period_datetimes(sub, sub)
    if period_start is None or period_end is None:
        raise SubscriptionMappingError(
            f"Subscription billing period not found for {subscription_id}"
        )

    status = SubscriptionStatus(sub.status)

    pricing = helpers.extract_subscription_pricing(sub)

    subscription_type = (
        SubscriptionType.PREMIUM
        if tier_kind == SubscriptionTierEnum.PREMIUM
        else SubscriptionType.PRO
    )

    return SubscriptionFields(
        stripe_subscription_id=subscription_id,
        customer_id=helpers.get_customer_id(sub),
        user_id=user_id,
        tier_id=tier_id,
        subscription_type=subscription_type,
        status=status,
        current_period_start=period_start,
        current_period_end=period_end,
        cancel_at_period_end=bool(sub.cancel_at_period_end),
        canceled_at=helpers.get_canceled_at(sub),
        ended_at=helpers.get_ended_at(sub),
        billing_cycle_anchor=helpers.get_billing_cycle_anchor(sub),
        stripe_price_id=pricing.price_id if pricing is not None else None,
        amount=pricing.unit_amount if pricing is not None else None,
        currency=pricing.currency if pricing is not None else None,
        interval=pricing.interval if pricing is not None else None,
        latest_invoice=helpers.get_latest_invoice_id(sub),
        default_payment_method=helpers.get_default_payment_method_id(sub),
    )


def apply_subscription_fields(
    target: PaidSubscription,
    fields: SubscriptionFields,
) -> None:
    """Copy `SubscriptionFields` onto a `PaidSubscription` row.

    Required (NOT NULL) columns overwrite unconditionally. Nullable
    columns with value `None` preserve the existing target value
    (legacy null-skip). Pricing applies atomically: when
    `stripe_price_id` is `None` the whole pricing tuple is left
    untouched, matching `extract_subscription_pricing(...) is None`.
    """
    target.stripe_subscription_id = fields.stripe_subscription_id
    target.user_id = fields.user_id
    target.tier_id = fields.tier_id
    target.subscription_type = fields.subscription_type
    target.status = fields.status
    target.current_period_start = fields.current_period_start
    target.current_period_end = fields.current_period_end
    target.cancel_at_period_end = fields.cancel_at_period_end

    # `customer_id` is NOT NULL on the model, but Stripe sometimes omits
    # it on legacy fixtures — keep the null-skip to avoid clobbering an
    # existing valid value with `None`.
    if fields.customer_id is not None:
        target.customer_id = fields.customer_id
    if fields.canceled_at is not None:
        target.canceled_at = fields.canceled_at
    if fields.ended_at is not None:
        target.ended_at = fields.ended_at
    if fields.billing_cycle_anchor is not None:
        target.billing_cycle_anchor = fields.billing_cycle_anchor
    if fields.latest_invoice is not None:
        target.latest_invoice = fields.latest_invoice
    if fields.default_payment_method is not None:
        target.default_payment_method = fields.default_payment_method

    if fields.stripe_price_id is not None:
        # All four pricing fields are populated together by
        # `extract_subscription_pricing`, so this branch is total.
        assert fields.amount is not None
        assert fields.currency is not None
        assert fields.interval is not None
        target.stripe_price_id = fields.stripe_price_id
        target.amount = fields.amount
        target.currency = fields.currency
        target.interval = fields.interval
