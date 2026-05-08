from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from loguru import logger

from virtual_labs.infrastructure.db.models import (
    SubscriptionStatus,
    SubscriptionType,
)

PostCommitRunner = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CardDetails:
    brand: str
    last4: str
    exp_month: int
    exp_year: int


@dataclass(frozen=True, slots=True)
class ChargeInfo:
    charge_id: str | None
    receipt_url: str | None


@dataclass(frozen=True, slots=True)
class InvoiceAmounts:
    amount_paid: int
    subtotal: int
    tax: int
    total: int
    currency: str


@dataclass(frozen=True, slots=True)
class PaymentIntentAmounts:
    amount: int
    subtotal: int
    tax: int
    total: int
    currency: str


@dataclass(frozen=True, slots=True)
class InvoicePeriod:
    start: int | None
    end: int | None


@dataclass(frozen=True, slots=True)
class SubscriptionPricing:
    """Pricing fields from a Stripe Subscription's first item.

    Only constructed when the subscription actually has an item — preserves
    the legacy 'don't touch pricing fields when items are missing' behavior.
    """

    price_id: str | None
    product_id: str | None
    unit_amount: int
    currency: str
    interval: str


@dataclass(frozen=True, slots=True)
class SubscriptionFields:
    """Pure mapping of a `stripe.Subscription` onto local DB columns.

    Built by `subscription_mapping.map_stripe_subscription_to_db`. The
    orchestrator copies these fields onto a `PaidSubscription` row inside the
    per-event DB transaction. No I/O, no repository access — fully unit-testable
    against `convert_to_stripe_object` fixtures.

    Optional fields use `None` to mean "leave the existing local value
    untouched" (legacy null-skip semantics), matching `_set_if` / `_apply_if`
    behavior in webhook.py.
    """

    # Identity / linkage
    stripe_subscription_id: str
    customer_id: str | None
    user_id: UUID
    tier_id: UUID
    subscription_type: SubscriptionType

    # Lifecycle
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    canceled_at: datetime | None
    ended_at: datetime | None
    billing_cycle_anchor: datetime | None

    # Pricing (None when subscription has no items — preserves legacy skip)
    stripe_price_id: str | None
    amount: int | None
    currency: str | None
    interval: str | None

    # Stripe references
    latest_invoice: str | None
    default_payment_method: str | None


@dataclass(slots=True)
class PostCommitActions:
    """Side-effects to run after the DB transaction commits successfully.

    Failures of individual actions are logged but do not roll back the
    already-committed DB state. This matches today's behavior where Keycloak
    and accounting calls are best-effort relative to the DB write.
    """

    actions: list[PostCommitRunner] = field(default_factory=list)

    def add(self, action: PostCommitRunner) -> None:
        self.actions.append(action)

    async def run(self) -> None:
        for action in self.actions:
            try:
                await action()
            except Exception as exc:
                logger.warning(f"Post-commit action failed: {exc}")
