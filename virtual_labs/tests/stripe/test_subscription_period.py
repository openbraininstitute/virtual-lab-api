from datetime import datetime
from types import SimpleNamespace

from virtual_labs.infrastructure.stripe.duration import (
    get_subscription_period_datetimes,
)


def test_extracts_period_from_subscription_root() -> None:
    start, end = get_subscription_period_datetimes(
        {
            "current_period_start": 1778050545,
            "current_period_end": 1780728945,
        }
    )

    assert start == datetime(2026, 5, 6, 6, 55, 45)
    assert end == datetime(2026, 6, 6, 6, 55, 45)


def test_extracts_period_from_first_subscription_item_when_root_is_missing() -> None:
    start, end = get_subscription_period_datetimes(
        {
            "items": {
                "data": [
                    {
                        "current_period_start": 1778050545,
                        "current_period_end": 1780728945,
                    }
                ]
            }
        }
    )

    assert start == datetime(2026, 5, 6, 6, 55, 45)
    assert end == datetime(2026, 6, 6, 6, 55, 45)


def test_extracts_period_from_event_subscription_when_fetched_subscription_omits_it() -> (
    None
):
    start, end = get_subscription_period_datetimes(
        {"id": "sub_123"},
        {
            "current_period_start": 1778050545,
            "current_period_end": 1780728945,
        },
    )

    assert start == datetime(2026, 5, 6, 6, 55, 45)
    assert end == datetime(2026, 6, 6, 6, 55, 45)


def test_extracts_period_from_expanded_invoice_line_when_subscription_fields_are_missing() -> (
    None
):
    start, end = get_subscription_period_datetimes(
        {
            "latest_invoice": {
                "lines": {
                    "data": [
                        {
                            "period": {
                                "start": 1778050545,
                                "end": 1780728945,
                            }
                        }
                    ]
                }
            }
        }
    )

    assert start == datetime(2026, 5, 6, 6, 55, 45)
    assert end == datetime(2026, 6, 6, 6, 55, 45)


def test_supports_stripe_like_objects() -> None:
    stripe_subscription = SimpleNamespace(
        current_period_start=None,
        current_period_end=None,
        items=SimpleNamespace(
            data=[
                SimpleNamespace(
                    current_period_start=1778050545,
                    current_period_end=1780728945,
                )
            ]
        ),
    )

    start, end = get_subscription_period_datetimes(stripe_subscription)

    assert start == datetime(2026, 5, 6, 6, 55, 45)
    assert end == datetime(2026, 6, 6, 6, 55, 45)
