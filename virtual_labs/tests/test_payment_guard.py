"""Truth-table tests for the CH country-mismatch guard.

The guard replaces a Stripe Radar rule:

    block iff CH appears on exactly one of
      (card issuer country, payload billing country)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from virtual_labs.infrastructure.settings import settings
from virtual_labs.services.payment_guard import (
    CountryMismatchBlocked,
    ensure_ch_country_match,
)


class _FakeStripeRepo:
    """Stub returning a PaymentMethod-shaped object with the given card country."""

    def __init__(self, card_country: str | None) -> None:
        self._card_country = card_country

    async def get_payment_method(self, payment_method_id: str) -> Any:
        card = (
            SimpleNamespace(country=self._card_country)
            if self._card_country is not None
            else None
        )
        return SimpleNamespace(card=card)


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BILLING_BLOCK_CH_COUNTRY_MISMATCH", True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "card_country, billing_country",
    [
        ("CH", "CH"),
        ("FR", "FR"),
        ("US", "DE"),
        (None, None),
        (None, "FR"),
        ("FR", None),
    ],
)
async def test_allows_when_either_both_or_neither_are_ch(
    card_country: str | None, billing_country: str | None
) -> None:
    repo = _FakeStripeRepo(card_country)
    # No exception means allow.
    await ensure_ch_country_match(
        repo,  # type: ignore[arg-type]
        payment_method_id="pm_test",
        billing_country=billing_country,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "card_country, billing_country",
    [
        ("CH", "FR"),
        ("FR", "CH"),
        ("CH", None),
        (None, "CH"),
        ("CH", ""),
        ("ch", "FR"),  # case-insensitive
        ("FR", "ch"),
    ],
)
async def test_blocks_when_exactly_one_side_is_ch(
    card_country: str | None, billing_country: str | None
) -> None:
    repo = _FakeStripeRepo(card_country)
    with pytest.raises(CountryMismatchBlocked) as exc_info:
        await ensure_ch_country_match(
            repo,  # type: ignore[arg-type]
            payment_method_id="pm_test",
            billing_country=billing_country,
        )
    assert exc_info.value.card_country == (card_country or "")
    assert exc_info.value.billing_country == (billing_country or "")


@pytest.mark.asyncio
async def test_flag_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BILLING_BLOCK_CH_COUNTRY_MISMATCH", False)
    # Would otherwise be a hard block; flag-off means allow.
    repo = _FakeStripeRepo("CH")
    await ensure_ch_country_match(
        repo,  # type: ignore[arg-type]
        payment_method_id="pm_test",
        billing_country="FR",
    )
