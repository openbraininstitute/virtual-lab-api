"""Unit tests for the typed Stripe webhook extractors.

These tests construct Stripe SDK objects via `stripe.util.convert_to_stripe_object`
on plain JSON shapes — that's the same mechanism Stripe uses for webhook
payloads, so the test inputs match what production sees.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
import stripe
from stripe import convert_to_stripe_object

from virtual_labs.domain.billing import TaxBehavior, TaxStatus
from virtual_labs.infrastructure.db.models import PaymentStatus
from virtual_labs.infrastructure.stripe import helpers as extractors
from virtual_labs.infrastructure.stripe.types import (
    CardDetails,
    ChargeInfo,
    InvoiceAmounts,
    InvoicePeriod,
    PaymentIntentAmounts,
)


def _to_obj(payload: dict[str, Any]) -> Any:
    return convert_to_stripe_object(payload)


# ---------------------------------------------------------------------------
# Event-level
# ---------------------------------------------------------------------------


def test_event_type_and_id_use_direct_typed_access() -> None:
    """Sanity-check that `event.type` and `event.id` are typed and present.

    These are accessed directly (no wrapper) — Stripe SDK already typed them.
    """
    event = _to_obj(
        {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "object": "subscription"}},
        }
    )
    assert event.type == "customer.subscription.updated"
    assert event.id == "evt_1"


def test_is_standalone_event_true() -> None:
    event = _to_obj(
        {
            "id": "evt_1",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_1",
                    "object": "payment_intent",
                    "metadata": {"standalone": "true"},
                }
            },
        }
    )
    assert extractors.is_standalone_event(event) is True


def test_is_standalone_event_false_when_metadata_missing() -> None:
    event = _to_obj(
        {
            "id": "evt_1",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_1", "object": "payment_intent"}},
        }
    )
    assert extractors.is_standalone_event(event) is False


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def test_get_metadata_returns_empty_dict_for_missing() -> None:
    obj = _to_obj({"id": "x", "object": "subscription"})
    assert extractors.get_metadata(obj) == {}


def test_get_customer_id_handles_string_and_object() -> None:
    sub_with_id_only = _to_obj(
        {"id": "sub_1", "object": "subscription", "customer": "cus_123"}
    )
    sub_expanded = _to_obj(
        {
            "id": "sub_1",
            "object": "subscription",
            "customer": {"id": "cus_456", "object": "customer"},
        }
    )
    assert extractors.get_customer_id(sub_with_id_only) == "cus_123"
    assert extractors.get_customer_id(sub_expanded) == "cus_456"


def test_get_customer_id_returns_none_when_missing() -> None:
    sub = _to_obj({"id": "sub_1", "object": "subscription"})
    assert extractors.get_customer_id(sub) is None


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


def _subscription_payload(
    *,
    items_data: list[dict[str, Any]] | None = None,
    latest_invoice: Any = None,
    default_payment_method: Any = None,
    canceled_at: int | None = None,
    ended_at: int | None = None,
    billing_cycle_anchor: int | None = None,
    cancel_at_period_end: bool = False,
    currency: str = "usd",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "sub_1",
        "object": "subscription",
        "currency": currency,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {"object": "list", "data": items_data or []},
    }
    if latest_invoice is not None:
        payload["latest_invoice"] = latest_invoice
    if default_payment_method is not None:
        payload["default_payment_method"] = default_payment_method
    if canceled_at is not None:
        payload["canceled_at"] = canceled_at
    if ended_at is not None:
        payload["ended_at"] = ended_at
    if billing_cycle_anchor is not None:
        payload["billing_cycle_anchor"] = billing_cycle_anchor
    return payload


def test_extract_subscription_pricing_with_expanded_product() -> None:
    sub = _to_obj(
        _subscription_payload(
            items_data=[
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "price": {
                        "id": "price_1",
                        "object": "price",
                        "product": {"id": "prod_1", "object": "product"},
                        "unit_amount": 1500,
                        "currency": "usd",
                        "recurring": {"interval": "month"},
                    },
                }
            ]
        )
    )
    pricing = extractors.extract_subscription_pricing(sub)
    assert pricing is not None
    assert pricing.product_id == "prod_1"
    assert pricing.price_id == "price_1"
    assert pricing.unit_amount == 1500
    assert pricing.currency == "usd"
    assert pricing.interval == "month"
    # The single-product helper still exists and matches
    assert extractors.get_product_id_from_subscription(sub) == "prod_1"


def test_extract_subscription_pricing_with_unexpanded_product() -> None:
    sub = _to_obj(
        _subscription_payload(
            items_data=[
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "price": {
                        "id": "price_1",
                        "object": "price",
                        "product": "prod_str",
                        "unit_amount": 0,
                    },
                }
            ]
        )
    )
    pricing = extractors.extract_subscription_pricing(sub)
    assert pricing is not None
    assert pricing.product_id == "prod_str"
    assert pricing.unit_amount == 0
    assert pricing.interval == "month"  # default when recurring is missing
    assert pricing.currency == "chf"  # default when price.currency is missing


def test_extract_subscription_pricing_returns_none_when_no_items() -> None:
    sub = _to_obj(_subscription_payload(items_data=[]))
    assert extractors.extract_subscription_pricing(sub) is None
    assert extractors.get_product_id_from_subscription(sub) is None
    assert extractors.has_subscription_items(sub) is False


def test_latest_invoice_id_handles_expanded_and_string() -> None:
    sub_string = _to_obj(_subscription_payload(latest_invoice="in_str"))
    sub_expanded = _to_obj(
        _subscription_payload(latest_invoice={"id": "in_obj", "object": "invoice"})
    )
    sub_missing = _to_obj(_subscription_payload())
    assert extractors.get_latest_invoice_id(sub_string) == "in_str"
    assert extractors.get_latest_invoice_id(sub_expanded) == "in_obj"
    assert extractors.get_latest_invoice_id(sub_missing) is None


def test_default_payment_method_id_handles_expanded_and_string() -> None:
    sub_string = _to_obj(_subscription_payload(default_payment_method="pm_str"))
    sub_expanded = _to_obj(
        _subscription_payload(
            default_payment_method={"id": "pm_obj", "object": "payment_method"}
        )
    )
    assert extractors.get_default_payment_method_id(sub_string) == "pm_str"
    assert extractors.get_default_payment_method_id(sub_expanded) == "pm_obj"


def test_get_canceled_at_returns_naive_datetime() -> None:
    ts = 1_700_000_000
    sub = _to_obj(_subscription_payload(canceled_at=ts))
    result = extractors.get_canceled_at(sub)
    assert result is not None
    assert result.timestamp() == pytest.approx(float(ts), abs=1.0)


def test_get_canceled_at_returns_none_when_missing() -> None:
    sub = _to_obj(_subscription_payload())
    assert extractors.get_canceled_at(sub) is None
    assert extractors.get_ended_at(sub) is None
    assert extractors.get_billing_cycle_anchor(sub) is None


def test_get_currency_default_when_missing() -> None:
    sub = _to_obj({"id": "sub_1", "object": "subscription"})
    assert extractors.get_currency(sub, default="chf") == "chf"


def test_cancel_at_period_end_uses_direct_typed_access() -> None:
    sub = _to_obj(_subscription_payload(cancel_at_period_end=True))
    # No wrapper — Subscription.cancel_at_period_end is typed `bool`
    assert sub.cancel_at_period_end is True


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


def _invoice_payload(
    *,
    subscription: Any = None,
    payment_intent: Any = None,
    metadata: dict[str, str] | None = None,
    sub_details_metadata: dict[str, str] | None = None,
    lines_data: list[dict[str, Any]] | None = None,
    total_tax_amounts: list[dict[str, Any]] | None = None,
    amount_paid: int = 0,
    subtotal: int = 0,
    currency: str = "chf",
    customer_address: dict[str, Any] | None = None,
    invoice_pdf: str | None = None,
    api_shape: str = "legacy",
) -> dict[str, Any]:
    """Build an invoice payload in either API shape.

    `api_shape` controls where subscription-related fields land:
      - "legacy" (default): top-level `subscription`, `payment_intent`,
        `subscription_details` — preserved for backward-compat coverage
        of older Stripe accounts.
      - "billing_2024_04_10": Billing model layout — fields nest under
        `parent.subscription_details` and `confirmation_secret`. Match
        the shape production receives on API 2024-04-10+.
    """
    if api_shape not in ("legacy", "billing_2024_04_10"):
        raise ValueError(f"unknown api_shape: {api_shape}")

    payload: dict[str, Any] = {
        "id": "in_1",
        "object": "invoice",
        "amount_paid": amount_paid,
        "subtotal": subtotal,
        "currency": currency,
        "lines": {"object": "list", "data": lines_data or []},
        "total_tax_amounts": total_tax_amounts or [],
    }

    if api_shape == "legacy":
        if subscription is not None:
            payload["subscription"] = subscription
        if payment_intent is not None:
            payload["payment_intent"] = payment_intent
        if sub_details_metadata is not None:
            payload["subscription_details"] = {"metadata": sub_details_metadata}
    else:  # billing_2024_04_10
        sub_details: dict[str, Any] = {}
        if subscription is not None:
            sub_details["subscription"] = subscription
        if sub_details_metadata is not None:
            sub_details["metadata"] = sub_details_metadata
        if sub_details:
            payload["parent"] = {
                "type": "subscription_details",
                "subscription_details": sub_details,
            }
        if payment_intent is not None:
            payload["confirmation_secret"] = {"payment_intent": payment_intent}

    if metadata is not None:
        payload["metadata"] = metadata
    if customer_address is not None:
        payload["customer_address"] = customer_address
    if invoice_pdf is not None:
        payload["invoice_pdf"] = invoice_pdf
    return payload


def test_subscription_id_from_invoice_handles_string_and_object() -> None:
    inv_str = _to_obj(_invoice_payload(subscription="sub_str"))
    inv_obj = _to_obj(
        _invoice_payload(subscription={"id": "sub_obj", "object": "subscription"})
    )
    assert extractors.get_subscription_id_from_invoice(inv_str) == "sub_str"
    assert extractors.get_subscription_id_from_invoice(inv_obj) == "sub_obj"


def test_payment_intent_id_from_invoice_handles_string_and_object() -> None:
    inv_str = _to_obj(_invoice_payload(payment_intent="pi_str"))
    inv_obj = _to_obj(
        _invoice_payload(payment_intent={"id": "pi_obj", "object": "payment_intent"})
    )
    assert extractors.get_payment_intent_id_from_invoice(inv_str) == "pi_str"
    assert extractors.get_payment_intent_id_from_invoice(inv_obj) == "pi_obj"


def test_subscription_id_falls_back_to_parent_subscription_details() -> None:
    """Stripe Billing model relocates `subscription` to `parent.subscription_details`."""
    inv = _to_obj(
        {
            "id": "in_1",
            "object": "invoice",
            "parent": {
                "type": "subscription_details",
                "subscription_details": {"subscription": "sub_billing_model"},
            },
        }
    )
    assert extractors.get_subscription_id_from_invoice(inv) == "sub_billing_model"


def test_subscription_id_falls_back_to_line_item_parent() -> None:
    """Last-resort: read from the first line's `parent.subscription_item_details`."""
    inv = _to_obj(
        {
            "id": "in_1",
            "object": "invoice",
            "lines": {
                "object": "list",
                "data": [
                    {
                        "id": "il_1",
                        "object": "line_item",
                        "parent": {
                            "type": "subscription_item_details",
                            "subscription_item_details": {
                                "subscription": "sub_from_line",
                            },
                        },
                    }
                ],
            },
        }
    )
    assert extractors.get_subscription_id_from_invoice(inv) == "sub_from_line"


def test_subscription_id_legacy_top_level_takes_precedence() -> None:
    """When both shapes are present (rare), legacy field wins for back-compat."""
    inv = _to_obj(
        {
            "id": "in_1",
            "object": "invoice",
            "subscription": "sub_legacy",
            "parent": {
                "subscription_details": {"subscription": "sub_billing_model"},
            },
        }
    )
    assert extractors.get_subscription_id_from_invoice(inv) == "sub_legacy"


def test_invoice_payload_billing_shape_round_trips_through_extractors() -> None:
    """Same fixture, new shape — confirms extractors agree on the value."""
    inv = _to_obj(
        _invoice_payload(
            api_shape="billing_2024_04_10",
            subscription="sub_billing",
            payment_intent="pi_billing",
            sub_details_metadata={"user_id": "u_billing"},
        )
    )
    assert extractors.get_subscription_id_from_invoice(inv) == "sub_billing"
    assert extractors.get_payment_intent_id_from_invoice(inv) == "pi_billing"
    assert extractors.get_invoice_user_id(inv) == "u_billing"


def test_get_invoice_user_id_reads_parent_subscription_details() -> None:
    """User id lives under `parent.subscription_details.metadata` in Billing model."""
    inv = _to_obj(
        {
            "id": "in_1",
            "object": "invoice",
            "parent": {
                "subscription_details": {"metadata": {"user_id": "u_from_parent"}},
            },
        }
    )
    assert extractors.get_invoice_user_id(inv) == "u_from_parent"


def test_get_invoice_user_id_prefers_subscription_details() -> None:
    inv = _to_obj(
        _invoice_payload(
            sub_details_metadata={"user_id": "u_from_sub_details"},
            metadata={"user_id": "u_from_top"},
        )
    )
    assert extractors.get_invoice_user_id(inv) == "u_from_sub_details"


def test_get_invoice_user_id_falls_back_to_top_metadata() -> None:
    inv = _to_obj(_invoice_payload(metadata={"user_id": "u_top"}))
    assert extractors.get_invoice_user_id(inv) == "u_top"


def test_get_invoice_user_id_returns_none_when_absent() -> None:
    inv = _to_obj(_invoice_payload())
    assert extractors.get_invoice_user_id(inv) is None


def test_get_invoice_period_first_line() -> None:
    inv = _to_obj(
        _invoice_payload(
            lines_data=[
                {
                    "id": "li_1",
                    "object": "line_item",
                    "period": {"start": 1_000_000, "end": 2_000_000},
                }
            ]
        )
    )
    assert extractors.get_invoice_period(inv) == InvoicePeriod(
        start=1_000_000, end=2_000_000
    )


def test_get_invoice_period_no_lines() -> None:
    inv = _to_obj(_invoice_payload(lines_data=[]))
    assert extractors.get_invoice_period(inv) == InvoicePeriod(start=None, end=None)


def test_get_invoice_amounts_zero_default() -> None:
    inv = _to_obj(_invoice_payload(amount_paid=0, subtotal=0))
    a = extractors.get_invoice_amounts(inv, default_currency="chf")
    assert a == InvoiceAmounts(
        amount_paid=0, subtotal=0, tax=0, total=0, currency="chf"
    )


def test_get_invoice_amounts_with_tax() -> None:
    inv = _to_obj(
        _invoice_payload(
            amount_paid=1500,
            subtotal=1200,
            total_tax_amounts=[
                {"amount": 100, "inclusive": False},
                {"amount": 200, "inclusive": False},
            ],
            currency="usd",
        )
    )
    a = extractors.get_invoice_amounts(inv, default_currency="chf")
    assert a == InvoiceAmounts(
        amount_paid=1500, subtotal=1200, tax=300, total=1500, currency="usd"
    )


def test_get_total_tax_from_invoice_empty_list() -> None:
    inv = _to_obj(_invoice_payload(total_tax_amounts=[]))
    assert extractors.get_total_tax_from_invoice(inv) == 0


def test_merge_invoice_metadata_precedence() -> None:
    event_data = _to_obj(
        _invoice_payload(
            sub_details_metadata={"a": "1", "b": "1"},
            metadata={"b": "2", "c": "2"},
        )
    )
    invoice = _to_obj(
        _invoice_payload(
            sub_details_metadata={"c": "3", "d": "3"},
            metadata={"d": "4", "e": "4"},
        )
    )
    merged = extractors.merge_invoice_metadata(event_data, invoice)
    # later wins
    assert merged == {"a": "1", "b": "2", "c": "3", "d": "4", "e": "4"}


def test_merge_invoice_metadata_no_invoice() -> None:
    event_data = _to_obj(
        _invoice_payload(metadata={"a": "1"}, sub_details_metadata={"b": "2"})
    )
    merged = extractors.merge_invoice_metadata(event_data, None)
    assert merged == {"a": "1", "b": "2"}


def test_get_invoice_customer_address() -> None:
    inv = _to_obj(
        _invoice_payload(
            customer_address={
                "country": "CH",
                "city": "Geneva",
                "line1": "Rue 1",
                "line2": None,
                "postal_code": "1200",
                "state": None,
            }
        )
    )
    addr = extractors.get_invoice_customer_address(inv)
    assert addr is not None
    assert addr["country"] == "CH"
    assert addr["city"] == "Geneva"
    assert "line2" not in addr  # null filtered


def test_invoice_pdf_uses_direct_typed_access() -> None:
    inv = _to_obj(_invoice_payload(invoice_pdf="https://stripe.example/pdf"))
    # No wrapper — Invoice.invoice_pdf is typed `Optional[str]`
    assert inv.invoice_pdf == "https://stripe.example/pdf"


def test_get_product_and_price_id_from_invoice_first_line() -> None:
    inv = _to_obj(
        _invoice_payload(
            lines_data=[
                {
                    "id": "li_1",
                    "object": "line_item",
                    "period": {"start": 1, "end": 2},
                    "price": {
                        "id": "price_x",
                        "object": "price",
                        "product": "prod_x",
                    },
                }
            ]
        )
    )
    assert extractors.get_product_id_from_invoice(inv) == "prod_x"
    assert extractors.get_price_id_from_invoice(inv) == "price_x"


# ---------------------------------------------------------------------------
# PaymentIntent
# ---------------------------------------------------------------------------


def _payment_intent_payload(
    *,
    amount: int = 0,
    currency: str = "usd",
    metadata: dict[str, str] | None = None,
    payment_method: Any = None,
    latest_charge: Any = None,
    customer: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "pi_1",
        "object": "payment_intent",
        "amount": amount,
        "currency": currency,
    }
    if metadata is not None:
        payload["metadata"] = metadata
    if payment_method is not None:
        payload["payment_method"] = payment_method
    if latest_charge is not None:
        payload["latest_charge"] = latest_charge
    if customer is not None:
        payload["customer"] = customer
    return payload


def test_get_card_details_when_expanded() -> None:
    pi = _to_obj(
        _payment_intent_payload(
            payment_method={
                "id": "pm_1",
                "object": "payment_method",
                "type": "card",
                "card": {
                    "brand": "visa",
                    "last4": "4242",
                    "exp_month": 12,
                    "exp_year": 2030,
                },
            }
        )
    )
    assert extractors.get_card_details(pi) == CardDetails(
        brand="visa", last4="4242", exp_month=12, exp_year=2030
    )


def test_get_card_details_returns_none_when_payment_method_is_id_string() -> None:
    pi = _to_obj(_payment_intent_payload(payment_method="pm_unexpanded"))
    assert extractors.get_card_details(pi) is None


def test_get_card_details_falls_back_to_last_payment_error_for_failed_intent() -> None:
    """Failed PaymentIntents (Radar block, declined card, etc.) null out
    `payment_method` and stash the attempted PM under
    `last_payment_error.payment_method`. Card details must still be
    readable so the failure-path webhook can record them."""
    payload = _payment_intent_payload(payment_method=None)
    payload["last_payment_error"] = {
        "code": "card_declined",
        "payment_method": {
            "id": "pm_failed",
            "object": "payment_method",
            "type": "card",
            "card": {
                "brand": "visa",
                "last4": "4242",
                "exp_month": 1,
                "exp_year": 2028,
            },
        },
    }
    pi = _to_obj(payload)
    assert extractors.get_card_details(pi) == CardDetails(
        brand="visa", last4="4242", exp_month=1, exp_year=2028
    )


def test_get_card_details_returns_none_when_no_card_block() -> None:
    pi = _to_obj(
        _payment_intent_payload(
            payment_method={"id": "pm_1", "object": "payment_method", "type": "klarna"}
        )
    )
    assert extractors.get_card_details(pi) is None


def test_get_charge_info_when_expanded() -> None:
    pi = _to_obj(
        _payment_intent_payload(
            latest_charge={
                "id": "ch_1",
                "object": "charge",
                "receipt_url": "https://stripe.example/receipt",
            }
        )
    )
    assert extractors.get_charge_info(pi) == ChargeInfo(
        charge_id="ch_1", receipt_url="https://stripe.example/receipt"
    )


def test_get_charge_info_returns_none_when_unexpanded() -> None:
    pi = _to_obj(_payment_intent_payload(latest_charge="ch_str"))
    assert extractors.get_charge_info(pi) is None


def test_get_charge_info_returns_none_when_missing() -> None:
    pi = _to_obj(_payment_intent_payload())
    assert extractors.get_charge_info(pi) is None


def test_get_payment_intent_amounts_metadata_overrides() -> None:
    pi = _to_obj(_payment_intent_payload(amount=1500, currency="usd"))
    metadata = {
        "amount_subtotal": "1200",
        "amount_tax": "300",
        "amount_total": "1500",
    }
    a = extractors.get_payment_intent_amounts(pi, metadata, default_currency="usd")
    assert a == PaymentIntentAmounts(
        amount=1500, subtotal=1200, tax=300, total=1500, currency="usd"
    )


def test_get_payment_intent_amounts_falls_back_to_amount_when_metadata_missing() -> (
    None
):
    pi = _to_obj(_payment_intent_payload(amount=900))
    a = extractors.get_payment_intent_amounts(pi, {}, default_currency="usd")
    assert a == PaymentIntentAmounts(
        amount=900, subtotal=900, tax=0, total=900, currency="usd"
    )


# ---------------------------------------------------------------------------
# Status conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event_type,expected",
    [
        ("invoice.payment_succeeded", PaymentStatus.SUCCEEDED),
        ("payment_intent.succeeded", PaymentStatus.SUCCEEDED),
        ("invoice.paid", PaymentStatus.SUCCEEDED),
        ("invoice.payment_failed", PaymentStatus.FAILED),
        ("payment_intent.payment_failed", PaymentStatus.FAILED),
        ("payment_intent.canceled", PaymentStatus.FAILED),
        ("customer.subscription.updated", PaymentStatus.PENDING),
    ],
)
def test_payment_status_from_event_type(
    event_type: str, expected: PaymentStatus
) -> None:
    assert extractors.payment_status_from_event_type(event_type) == expected


def test_tax_behavior_from_metadata_present_and_absent() -> None:
    assert extractors.tax_behavior_from_metadata({}) is None
    assert extractors.tax_behavior_from_metadata(
        {"tax_behavior": "exclusive"}
    ) == TaxBehavior("exclusive")


def test_tax_status_from_metadata_present_and_absent() -> None:
    assert extractors.tax_status_from_metadata({}) is None
    assert extractors.tax_status_from_metadata(
        {"tax_status": "calculated"}
    ) == TaxStatus("calculated")


# ---------------------------------------------------------------------------
# Smoke test: extractors are stable across runs (deterministic)
# ---------------------------------------------------------------------------


def test_event_obj_is_typed_subscription_at_runtime() -> None:
    """The runtime cast at the dispatch site is the contract this whole module
    relies on. Lock it down."""
    event = _to_obj(
        {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "object": "subscription"}},
        }
    )
    obj = event.data.object
    # In SDK 9.x convert_to_stripe_object dispatches by `object` field.
    assert isinstance(obj, stripe.Subscription)
    assert obj.id == "sub_1"


def test_smoke_no_extractor_raises_on_minimal_subscription() -> None:
    """All subscription extractors must tolerate a near-empty Stripe object."""
    sub = _to_obj({"id": "sub_1", "object": "subscription"})
    # Avoid attribute-error regressions
    extractors.get_metadata(sub)
    extractors.get_customer_id(sub)
    extractors.get_product_id_from_subscription(sub)
    extractors.extract_subscription_pricing(sub)
    extractors.has_subscription_items(sub)
    extractors.get_currency(sub, default="chf")
    extractors.get_latest_invoice_id(sub)
    extractors.get_default_payment_method_id(sub)
    extractors.get_canceled_at(sub)
    extractors.get_ended_at(sub)
    extractors.get_billing_cycle_anchor(sub)


def _ts() -> int:
    """Helper kept to silence import lint if removed during edits."""
    return int(time.time())
