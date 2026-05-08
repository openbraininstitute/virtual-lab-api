"""Unit tests for the pure `map_stripe_subscription_to_db` mapper.

The mapper is deliberately I/O-free, so these tests don't need a DB or a
Stripe stub — `convert_to_stripe_object` produces the same typed
`stripe.Subscription` shape that production receives, and the function
returns a plain `SubscriptionFields` dataclass we can introspect.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import stripe
from stripe import convert_to_stripe_object

from virtual_labs.infrastructure.db.models import (
    SubscriptionStatus,
    SubscriptionTierEnum,
    SubscriptionType,
)
from virtual_labs.infrastructure.stripe.mapping import (
    SubscriptionMappingError,
    apply_subscription_fields,
    map_stripe_subscription_to_db,
)


# Fixtures

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
TIER_ID = UUID("22222222-2222-2222-2222-222222222222")

# Period bounds expressed as Unix timestamps; conversion is naive-local
# datetime in `helpers._ts_to_datetime`, matching legacy behavior.
PERIOD_START_TS = 1_700_000_000
PERIOD_END_TS = 1_702_678_400


def _naive_utc(ts: int) -> datetime:
    """Match `subscription_period._to_naive_utc` semantics for test assertions."""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)


def _naive_local(ts: int) -> datetime:
    """Match `helpers._ts_to_datetime` semantics — local-tz naive."""
    return datetime.fromtimestamp(float(ts))


def _to_subscription(payload: dict[str, Any]) -> stripe.Subscription:
    """Cast `convert_to_stripe_object` output to the typed Subscription shape.

    Stripe's helper returns `StripeObject`; production code casts to the
    typed subclass at the dispatcher boundary, so tests do the same.
    """
    return cast(stripe.Subscription, convert_to_stripe_object(payload))


def _subscription_payload(
    *,
    items_data: list[dict[str, Any]] | None = None,
    status: str = "active",
    cancel_at_period_end: bool = False,
    customer: Any = "cus_1",
    canceled_at: int | None = None,
    ended_at: int | None = None,
    billing_cycle_anchor: int | None = None,
    latest_invoice: Any = None,
    default_payment_method: Any = None,
    current_period_start: int | None = PERIOD_START_TS,
    current_period_end: int | None = PERIOD_END_TS,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "sub_1",
        "object": "subscription",
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "customer": customer,
        "items": {
            "object": "list",
            # `or` would coerce an explicit empty list back to defaults; use
            # `is None` so callers can pass `[]` to mean "no items".
            "data": items_data if items_data is not None else _default_items(),
        },
    }
    if current_period_start is not None:
        payload["current_period_start"] = current_period_start
    if current_period_end is not None:
        payload["current_period_end"] = current_period_end
    if canceled_at is not None:
        payload["canceled_at"] = canceled_at
    if ended_at is not None:
        payload["ended_at"] = ended_at
    if billing_cycle_anchor is not None:
        payload["billing_cycle_anchor"] = billing_cycle_anchor
    if latest_invoice is not None:
        payload["latest_invoice"] = latest_invoice
    if default_payment_method is not None:
        payload["default_payment_method"] = default_payment_method
    return payload


def _default_items() -> list[dict[str, Any]]:
    return [
        {
            "id": "si_1",
            "object": "subscription_item",
            "price": {
                "id": "price_1",
                "object": "price",
                "product": "prod_1",
                "unit_amount": 1500,
                "currency": "chf",
                "recurring": {"interval": "month"},
            },
        }
    ]


# Mapping: required fields & happy path
def test_maps_required_fields_for_pro_tier() -> None:
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )

    assert fields.stripe_subscription_id == "sub_1"
    assert fields.user_id == USER_ID
    assert fields.tier_id == TIER_ID
    assert fields.subscription_type is SubscriptionType.PRO
    assert fields.status is SubscriptionStatus.ACTIVE
    assert fields.cancel_at_period_end is False
    assert fields.customer_id == "cus_1"
    assert fields.current_period_start == _naive_utc(PERIOD_START_TS)
    assert fields.current_period_end == _naive_utc(PERIOD_END_TS)


def test_premium_tier_resolves_to_premium_subscription_type() -> None:
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub,
        tier_id=TIER_ID,
        tier_kind=SubscriptionTierEnum.PREMIUM,
        user_id=USER_ID,
    )
    assert fields.subscription_type is SubscriptionType.PREMIUM


def test_pricing_fields_extracted_from_first_item() -> None:
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.stripe_price_id == "price_1"
    assert fields.amount == 1500
    assert fields.currency == "chf"
    assert fields.interval == "month"


def test_pricing_fields_are_none_when_subscription_has_no_items() -> None:
    """Preserves the legacy 'don't touch pricing fields when items are missing'."""
    sub = _to_subscription(_subscription_payload(items_data=[]))
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.stripe_price_id is None
    assert fields.amount is None
    assert fields.currency is None
    assert fields.interval is None


def test_optional_lifecycle_timestamps_extracted_when_present() -> None:
    sub = _to_subscription(
        _subscription_payload(
            cancel_at_period_end=True,
            canceled_at=PERIOD_START_TS - 100,
            ended_at=PERIOD_END_TS,
            billing_cycle_anchor=PERIOD_START_TS,
        )
    )
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.cancel_at_period_end is True
    assert fields.canceled_at == _naive_local(PERIOD_START_TS - 100)
    assert fields.ended_at == _naive_local(PERIOD_END_TS)
    assert fields.billing_cycle_anchor == _naive_local(PERIOD_START_TS)


def test_expandable_references_collapse_to_ids() -> None:
    sub = _to_subscription(
        _subscription_payload(
            latest_invoice={"id": "in_1", "object": "invoice"},
            default_payment_method="pm_card_1",
        )
    )
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.latest_invoice == "in_1"
    assert fields.default_payment_method == "pm_card_1"


def test_unexpanded_customer_id_is_kept_as_string() -> None:
    sub = _to_subscription(_subscription_payload(customer="cus_42"))
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.customer_id == "cus_42"


# Mapping: error paths
def test_missing_period_raises_mapping_error() -> None:
    """Both root and item period missing — should refuse to map."""
    sub = _to_subscription(
        _subscription_payload(
            current_period_start=None,
            current_period_end=None,
            items_data=[
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "price": _default_items()[0]["price"],
                    # No item-level period either.
                }
            ],
        )
    )
    with pytest.raises(SubscriptionMappingError, match="billing period"):
        map_stripe_subscription_to_db(
            sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
        )


def test_period_falls_back_to_item_when_root_missing() -> None:
    """Newer Stripe Billing emits the period on the item, not the root."""
    sub = _to_subscription(
        _subscription_payload(
            current_period_start=None,
            current_period_end=None,
            items_data=[
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "price": _default_items()[0]["price"],
                    "current_period_start": PERIOD_START_TS,
                    "current_period_end": PERIOD_END_TS,
                }
            ],
        )
    )
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    assert fields.current_period_start == _naive_utc(PERIOD_START_TS)
    assert fields.current_period_end == _naive_utc(PERIOD_END_TS)


# `apply_subscription_fields` — null-skip semantics
def _make_paid_subscription_stub() -> Any:
    """`PaidSubscription` is a SQLAlchemy model — we don't construct one
    directly to avoid pulling in DB metadata for unit tests. A dataclass
    isn't an option (slots collide with the assignment style), so we use
    a SimpleNamespace-shaped MagicMock with attribute equality."""
    target = MagicMock(spec=[])  # no auto-spec attrs; only what we set
    return target


def test_apply_writes_required_fields_unconditionally() -> None:
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    target = _make_paid_subscription_stub()

    apply_subscription_fields(target, fields)

    assert target.stripe_subscription_id == "sub_1"
    assert target.user_id == USER_ID
    assert target.tier_id == TIER_ID
    assert target.status is SubscriptionStatus.ACTIVE
    assert target.cancel_at_period_end is False


def test_apply_preserves_existing_pricing_when_subscription_has_no_items() -> None:
    """If the new mapping has no pricing, target's existing pricing must survive."""
    sub = _to_subscription(_subscription_payload(items_data=[]))
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )

    target = _make_paid_subscription_stub()
    target.stripe_price_id = "kept_price"
    target.amount = 999
    target.currency = "usd"
    target.interval = "year"

    apply_subscription_fields(target, fields)

    assert target.stripe_price_id == "kept_price"
    assert target.amount == 999
    assert target.currency == "usd"
    assert target.interval == "year"


def test_apply_overwrites_pricing_when_subscription_has_items() -> None:
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )

    target = _make_paid_subscription_stub()
    target.stripe_price_id = "old"
    target.amount = 1
    target.currency = "usd"
    target.interval = "year"

    apply_subscription_fields(target, fields)

    assert target.stripe_price_id == "price_1"
    assert target.amount == 1500
    assert target.currency == "chf"
    assert target.interval == "month"


def test_apply_preserves_existing_optional_when_mapping_is_none() -> None:
    sub = _to_subscription(_subscription_payload())  # no canceled_at / ended_at
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )

    target = _make_paid_subscription_stub()
    target.canceled_at = datetime(2020, 1, 1)
    target.ended_at = datetime(2020, 2, 1)
    target.latest_invoice = "in_kept"
    target.default_payment_method = "pm_kept"

    apply_subscription_fields(target, fields)

    assert target.canceled_at == datetime(2020, 1, 1)
    assert target.ended_at == datetime(2020, 2, 1)
    assert target.latest_invoice == "in_kept"
    assert target.default_payment_method == "pm_kept"


def test_apply_writes_optional_fields_when_mapping_supplies_them() -> None:
    sub = _to_subscription(
        _subscription_payload(
            canceled_at=PERIOD_START_TS,
            ended_at=PERIOD_END_TS,
            latest_invoice="in_42",
            default_payment_method="pm_42",
        )
    )
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )
    target = _make_paid_subscription_stub()

    apply_subscription_fields(target, fields)

    assert target.canceled_at == _naive_local(PERIOD_START_TS)
    assert target.ended_at == _naive_local(PERIOD_END_TS)
    assert target.latest_invoice == "in_42"
    assert target.default_payment_method == "pm_42"


def test_apply_isolated_from_user_id_change() -> None:
    """Running the same fields against a target with a different prior user_id
    overwrites — user_id is a required field."""
    sub = _to_subscription(_subscription_payload())
    fields = map_stripe_subscription_to_db(
        sub, tier_id=TIER_ID, tier_kind=SubscriptionTierEnum.PRO, user_id=USER_ID
    )

    target = _make_paid_subscription_stub()
    target.user_id = uuid4()

    apply_subscription_fields(target, fields)

    assert target.user_id == USER_ID
