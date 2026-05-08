"""Extract the billing period of a Stripe Subscription, with fallbacks.

Newer Stripe Billing payloads can omit `current_period_start` /
`current_period_end` at the subscription root while still exposing them on
subscription items or — failing that — on the latest invoice's first line
item period.

Public API: `get_subscription_period_datetimes(subscription, event_subscription)`
returning `(start, end)` as naive UTC datetimes.

Inputs are typed as `Any` because the helpers tolerate any of:
- `stripe.Subscription` (typed StripeObject from the SDK)
- a raw dict (the JSON shape Stripe webhook payloads expose)
- a `SimpleNamespace`-like object with attribute access (used in tests)

The duck-typing is delegated to the shared `_access.field_value` helper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from virtual_labs.infrastructure.stripe._access import field_value, first_item


def get_subscription_period_datetimes(
    stripe_subscription: Any,
    event_subscription: Any | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Best-effort billing-period start/end as naive UTC datetimes.

    Falls back through three sources in order:
    1. The subscription's root `current_period_*` fields.
    2. The first subscription item's `current_period_*` fields.
    3. The latest invoice's first line item's `period.start` / `period.end`.

    If those all miss on `stripe_subscription`, the same chain is tried on
    `event_subscription` (the inline copy from the webhook event), since
    Stripe sometimes populates one shape but not the other.
    """
    start, end = _period_from_source(stripe_subscription)

    if start is None or end is None:
        event_start, event_end = _period_from_source(event_subscription)
        start = start if start is not None else event_start
        end = end if end is not None else event_end

    return _to_naive_utc(start), _to_naive_utc(end)


def _period_from_source(source: Any) -> tuple[Any, Any]:
    """Walk the three fallback locations on `source` for period start/end."""
    if source is None:
        return None, None

    # Source #1 — subscription root
    start = field_value(source, "current_period_start")
    end = field_value(source, "current_period_end")
    if start is not None or end is not None:
        return start, end

    # Source #2 — first subscription item
    item = first_item(field_value(field_value(source, "items"), "data"))
    if item is not None:
        start = field_value(item, "current_period_start")
        end = field_value(item, "current_period_end")
        if start is not None or end is not None:
            return start, end

    # Source #3 — latest invoice's first line item period
    latest_invoice = field_value(source, "latest_invoice")
    line = first_item(field_value(field_value(latest_invoice, "lines"), "data"))
    period = field_value(line, "period")
    return field_value(period, "start"), field_value(period, "end")


def _to_naive_utc(value: Any) -> datetime | None:
    """Unix timestamp -> naive UTC datetime; tolerates None/empty/invalid."""
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(str(value)), tz=timezone.utc).replace(
            tzinfo=None
        )
    except (TypeError, ValueError, OverflowError):
        return None
