"""Typed extractors for Stripe webhook payloads.

Each function takes a typed Stripe SDK object (or a small union for
expandable fields) and returns a typed value with explicit fallbacks.
No `.get()` chains, no defensive `isinstance(..., dict)` checks at
call sites.

Stripe's `ExpandableField[T] = T | str` unions are narrowed inline
with `isinstance(field, str)` — when only the ID is available we
return it; when the object is expanded we read the typed attribute.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import stripe

from virtual_labs.domain.billing import TaxBehavior, TaxStatus
from virtual_labs.infrastructure.db.models import PaymentStatus
from virtual_labs.infrastructure.stripe._access import (
    expandable_id as _id_from_expandable,
)
from virtual_labs.infrastructure.stripe._access import (
    field_value as _field,
)
from virtual_labs.infrastructure.stripe.types import (
    CardDetails,
    ChargeInfo,
    InvoiceAmounts,
    InvoicePeriod,
    PaymentIntentAmounts,
    SubscriptionPricing,
)

SUBSCRIPTION_UPSERT_EVENTS: frozenset[str] = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.pending_update_applied",
        "customer.subscription.pending_update_expired",
    }
)

SUBSCRIPTION_DELETED_EVENTS: frozenset[str] = frozenset(
    {
        "customer.subscription.deleted",
    }
)

# Union of all subscription events the dispatcher cares about.
SUBSCRIPTION_UPDATE_EVENTS: frozenset[str] = (
    SUBSCRIPTION_UPSERT_EVENTS | SUBSCRIPTION_DELETED_EVENTS
)

INVOICE_PAYMENT_EVENTS: frozenset[str] = frozenset(
    {
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
)

STANDALONE_PAYMENT_EVENTS: frozenset[str] = frozenset(
    {
        "payment_intent.succeeded",
        "payment_intent.payment_failed",
        "payment_intent.canceled",
    }
)


DEFAULT_CURRENCY = "chf"


# Event-level
def resource_id_from_event(event: stripe.Event) -> str | None:
    """Return the id of the resource the event refers to.

    Bridge for the v1 → v2 events migration:
      - v1 (today): the resource is inlined as `event.data.object`; we read
        its `id`.
      - v2 (later): thin events carry only `event.related_object: {id, url,
        type}`; this function will pivot to that field. Every handler
        downstream consumes the resource id only, so swapping the source
        will be a single-function change.
    """
    obj = _field(_field(event, "data"), "object")
    return _id_from_expandable(obj) if obj is not None else None


def is_standalone_event(event: stripe.Event) -> bool:
    """Truthy `metadata.standalone` on the event's primary object.

    `event.type` and `event.id` are not wrapped — they're already typed
    `Literal[...]` and `str` on the Stripe SDK, so callers should access
    them directly.
    """
    obj = _field(_field(event, "data"), "object")
    if obj is None:
        return False
    return bool(get_metadata(obj).get("standalone"))


# Generic helpers on Stripe resources
def get_metadata(obj: object) -> dict[str, str]:
    """Return `obj.metadata` as a plain dict, never None."""
    metadata = _field(obj, "metadata")
    if not metadata:
        return {}
    return dict(metadata)


def get_customer_id(obj: object) -> str | None:
    return _id_from_expandable(_field(obj, "customer"))


# Subscription
def _first_subscription_item(sub: stripe.Subscription) -> object | None:
    items = _field(sub, "items")
    if items is None:
        return None
    data = _field(items, "data")
    if not data:
        return None
    return cast(object, data[0])


def get_first_price(sub: stripe.Subscription) -> object | None:
    item = _first_subscription_item(sub)
    if item is None:
        return None
    return cast("object | None", _field(item, "price"))


def get_product_id_from_subscription(sub: stripe.Subscription) -> str | None:
    pricing = extract_subscription_pricing(sub)
    return pricing.product_id if pricing is not None else None


def get_currency(obj: object, default: str = DEFAULT_CURRENCY) -> str:
    currency = _field(obj, "currency")
    if not currency:
        return default
    return str(currency)


def extract_subscription_pricing(
    sub: stripe.Subscription,
) -> SubscriptionPricing | None:
    """Extract pricing fields from the first subscription item.

    Returns `None` when the subscription has no items — callers should treat
    that as "leave pricing fields untouched on the local model" to match the
    legacy behavior.
    """
    price = get_first_price(sub)
    if price is None:
        return None

    raw_id = _field(price, "id")
    raw_amount = _field(price, "unit_amount")
    raw_currency = _field(price, "currency")
    recurring = _field(price, "recurring")
    raw_interval = _field(recurring, "interval") if recurring is not None else None

    return SubscriptionPricing(
        price_id=str(raw_id) if raw_id else None,
        product_id=_id_from_expandable(_field(price, "product")),
        unit_amount=int(raw_amount) if raw_amount is not None else 0,
        currency=str(raw_currency) if raw_currency else "chf",
        interval=str(raw_interval) if raw_interval else "month",
    )


def get_latest_invoice_id(sub: stripe.Subscription) -> str | None:
    return _id_from_expandable(_field(sub, "latest_invoice"))


def get_default_payment_method_id(sub: stripe.Subscription) -> str | None:
    return _id_from_expandable(_field(sub, "default_payment_method"))


def has_subscription_items(sub: stripe.Subscription) -> bool:
    """True when the subscription has at least one item (with a price)."""
    return _first_subscription_item(sub) is not None


def _ts_to_datetime(ts: object) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts))  # type: ignore[arg-type]


def get_canceled_at(sub: stripe.Subscription) -> datetime | None:
    return _ts_to_datetime(_field(sub, "canceled_at"))


def get_ended_at(sub: stripe.Subscription) -> datetime | None:
    return _ts_to_datetime(_field(sub, "ended_at"))


def get_billing_cycle_anchor(sub: stripe.Subscription) -> datetime | None:
    return _ts_to_datetime(_field(sub, "billing_cycle_anchor"))


# Invoice
def _invoice_subscription_details(invoice: stripe.Invoice) -> object | None:
    """Locate the `subscription_details` block on an Invoice.

    Stripe's Billing model (api_version 2024-04-10+) moved this from the
    invoice root to `invoice.parent.subscription_details`. We try the new
    shape first, then fall back to the legacy top-level field for older
    accounts. Returns whichever is populated; `None` when the invoice
    isn't tied to a subscription at all.
    """
    parent = _field(invoice, "parent")
    if parent is not None:
        details = _field(parent, "subscription_details")
        if details is not None:
            return cast(object, details)
    return cast("object | None", _field(invoice, "subscription_details"))


def _first_invoice_line(invoice: stripe.Invoice) -> object | None:
    lines = _field(invoice, "lines")
    if lines is None:
        return None
    data = _field(lines, "data")
    if not data:
        return None
    return cast(object, data[0])


def get_subscription_id_from_invoice(invoice: stripe.Invoice) -> str | None:
    """Read the subscription id off an Invoice with three fallbacks.

    Order:
      1. `invoice.subscription` (legacy top-level field)
      2. `invoice.parent.subscription_details.subscription` (new Billing model)
      3. First line item's `parent.subscription_item_details.subscription`
    """
    legacy = _id_from_expandable(_field(invoice, "subscription"))
    if legacy:
        return legacy

    details = _invoice_subscription_details(invoice)
    sub_id = _id_from_expandable(_field(details, "subscription"))
    if sub_id:
        return sub_id

    line = _first_invoice_line(invoice)
    line_parent = _field(line, "parent")
    item_details = _field(line_parent, "subscription_item_details")
    return _id_from_expandable(_field(item_details, "subscription"))


def get_payment_intent_id_from_invoice(invoice: stripe.Invoice) -> str | None:
    """Read the payment intent id off an Invoice.

    Falls back to `invoice.confirmation_secret.payment_intent` when the
    legacy top-level `payment_intent` field is absent (Billing model).
    """
    legacy = _id_from_expandable(_field(invoice, "payment_intent"))
    if legacy:
        return legacy

    confirmation = _field(invoice, "confirmation_secret")
    return _id_from_expandable(_field(confirmation, "payment_intent"))


def _sub_details_metadata(obj: object) -> dict[str, str]:
    """Metadata from `subscription_details`, accepting both old and new shapes.

    On an Invoice the block lives at `parent.subscription_details` in the
    new Billing model and at the root in the legacy shape; on other
    objects we still read the legacy top-level field directly. Either
    way we return the inner `metadata` dict.
    """
    if isinstance(obj, stripe.Invoice) or _field(obj, "object") == "invoice":
        details = _invoice_subscription_details(cast(stripe.Invoice, obj))
    else:
        details = _field(obj, "subscription_details")
    if details is None:
        return {}
    metadata = _field(details, "metadata")
    return dict(metadata) if metadata else {}


def get_invoice_user_id(invoice: stripe.Invoice) -> str | None:
    """user_id from `subscription_details.metadata`, else top-level metadata."""
    user_id = _sub_details_metadata(invoice).get("user_id")
    if user_id:
        return user_id
    return get_metadata(invoice).get("user_id")


def get_invoice_period(invoice: stripe.Invoice) -> InvoicePeriod:
    lines = _field(invoice, "lines")
    if lines is None:
        return InvoicePeriod(start=None, end=None)
    data = _field(lines, "data")
    if not data:
        return InvoicePeriod(start=None, end=None)
    period = _field(data[0], "period")
    if period is None:
        return InvoicePeriod(start=None, end=None)
    return InvoicePeriod(start=_field(period, "start"), end=_field(period, "end"))


def get_first_invoice_line_price(invoice: stripe.Invoice) -> object | None:
    lines = _field(invoice, "lines")
    if lines is None:
        return None
    data = _field(lines, "data")
    if not data:
        return None
    return cast("object | None", _field(data[0], "price"))


def get_product_id_from_invoice(invoice: stripe.Invoice) -> str | None:
    price = get_first_invoice_line_price(invoice)
    if price is None:
        return None
    return _id_from_expandable(_field(price, "product"))


def get_price_id_from_invoice(invoice: stripe.Invoice) -> str | None:
    price = get_first_invoice_line_price(invoice)
    if price is None:
        return None
    raw = _field(price, "id")
    return str(raw) if raw is not None else None


def get_invoice_amounts(
    invoice: stripe.Invoice, default_currency: str = "chf"
) -> InvoiceAmounts:
    """Mirror legacy `_update_payment_record` amount calculation.

    Legacy: amount = invoice.amount_paid (Invoice has no `.amount` attribute,
    so the legacy `event_data.get("amount", 0)` fallback was always 0);
    subtotal = invoice.subtotal or amount; tax = sum of total_tax_amounts;
    total = amount.
    """
    amount = int(_field(invoice, "amount_paid") or 0)
    subtotal_raw = _field(invoice, "subtotal")
    subtotal = int(subtotal_raw if subtotal_raw is not None else amount)
    tax = get_total_tax_from_invoice(invoice)
    return InvoiceAmounts(
        amount_paid=amount,
        subtotal=subtotal,
        tax=tax,
        total=amount,
        currency=get_currency(invoice, default=default_currency),
    )


def get_total_tax_from_invoice(invoice: stripe.Invoice) -> int:
    amounts = _field(invoice, "total_tax_amounts") or []
    total = 0
    for item in amounts:
        amount = _field(item, "amount")
        if amount is not None:
            total += int(amount)
    return total


def merge_invoice_metadata(
    event_data: stripe.Invoice,
    invoice: stripe.Invoice | None,
) -> dict[str, str]:
    """Replicate the precedence chain in legacy `_update_payment_record`.

    Order (later wins):
      1. event_data.subscription_details.metadata
      2. event_data.metadata
      3. invoice.subscription_details.metadata
      4. invoice.metadata
    """
    merged: dict[str, str] = {}
    merged.update(_sub_details_metadata(event_data))
    merged.update(get_metadata(event_data))
    if invoice is not None:
        merged.update(_sub_details_metadata(invoice))
        merged.update(get_metadata(invoice))
    return merged


def get_invoice_customer_address(invoice: stripe.Invoice) -> dict[str, str] | None:
    address = _field(invoice, "customer_address")
    if address is None:
        return None
    return _stripe_object_to_str_dict(address)


def get_customer_address(customer: stripe.Customer) -> dict[str, str] | None:
    address = _field(customer, "address")
    if address is None:
        return None
    return _stripe_object_to_str_dict(address)


def _stripe_object_to_str_dict(obj: object) -> dict[str, str]:
    """Materialize a (flat) StripeObject's non-null fields into a plain dict.

    `stripe.StripeObject` extends `dict`, so `dict(obj)` is a stable, public,
    non-deprecated snapshot of the top-level fields — sufficient for
    Address-shaped objects (which have no nested StripeObject children).
    """
    if isinstance(obj, dict):
        raw: dict[str, Any] = dict(obj)
    else:
        raw = {}
    return {str(k): v for k, v in raw.items() if v is not None}


# PaymentIntent
def get_card_details(pi: stripe.PaymentIntent) -> CardDetails | None:
    pm = _field(pi, "payment_method")
    if pm is None or isinstance(pm, str):
        return None
    card = _field(pm, "card")
    if card is None:
        return None
    brand = _field(card, "brand")
    last4 = _field(card, "last4")
    exp_month = _field(card, "exp_month")
    exp_year = _field(card, "exp_year")
    return CardDetails(
        brand=str(brand) if brand else "unknown",
        last4=str(last4) if last4 else "0000",
        exp_month=int(exp_month) if exp_month else 1,
        exp_year=int(exp_year) if exp_year else 2000,
    )


def get_charge_info(pi: stripe.PaymentIntent) -> ChargeInfo | None:
    charge = _field(pi, "latest_charge")
    if charge is None or isinstance(charge, str):
        return None
    charge_id_raw = _field(charge, "id")
    receipt_raw = _field(charge, "receipt_url")
    return ChargeInfo(
        charge_id=str(charge_id_raw) if charge_id_raw else None,
        receipt_url=str(receipt_raw) if receipt_raw else None,
    )


def get_payment_intent_amounts(
    pi: stripe.PaymentIntent,
    metadata: dict[str, str],
    default_currency: str = DEFAULT_CURRENCY,
) -> PaymentIntentAmounts:
    """Mirror legacy standalone-payment amount logic.

    Legacy:
      amount         = int(event_data.amount or 0)
      amount_subtotal = int(metadata.amount_subtotal or amount)
      amount_tax     = int(metadata.amount_tax or 0)
      amount_total   = int(metadata.amount_total or amount)
    """
    amount = int(_field(pi, "amount") or 0)
    subtotal = int(metadata.get("amount_subtotal") or amount)
    tax = int(metadata.get("amount_tax") or 0)
    total = int(metadata.get("amount_total") or amount)
    return PaymentIntentAmounts(
        amount=amount,
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency=get_currency(pi, default=default_currency),
    )


# Status / enum conversion
def payment_status_from_event_type(event_type: str) -> PaymentStatus:
    if "succeeded" in event_type or "paid" in event_type:
        return PaymentStatus.SUCCEEDED
    if "failed" in event_type or "canceled" in event_type:
        return PaymentStatus.FAILED
    return PaymentStatus.PENDING


def tax_behavior_from_metadata(metadata: dict[str, str]) -> TaxBehavior | None:
    raw = metadata.get("tax_behavior")
    if not raw:
        return None
    return TaxBehavior(raw)


def tax_status_from_metadata(metadata: dict[str, str]) -> TaxStatus | None:
    raw = metadata.get("tax_status")
    if not raw:
        return None
    return TaxStatus(raw)
