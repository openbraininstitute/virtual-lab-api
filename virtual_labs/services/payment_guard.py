"""Server-side replacement for Stripe Radar policy rules.

The Stripe Radar enforced the CH country-mismatch policy:

    IF (card_country='CH' OR billing_address_country='CH')
       AND NOT (card_country='CH' AND billing_address_country='CH')
    THEN block

The flag `BILLING_BLOCK_CH_COUNTRY_MISMATCH` lets ops cut over from Radar to
the API check
"""

from __future__ import annotations

from loguru import logger

from virtual_labs.infrastructure.settings import settings
from virtual_labs.repositories.stripe_repo import StripeRepository


class CountryMismatchBlocked(Exception):
    """Raised when the CH country-mismatch policy blocks a payment."""

    def __init__(self, card_country: str, billing_country: str) -> None:
        self.card_country = card_country
        self.billing_country = billing_country
        super().__init__(
            f"CH country mismatch: card_country={card_country or '?'}, "
            f"billing_country={billing_country or '?'}"
        )


async def ensure_ch_country_match(
    stripe_service: StripeRepository,
    payment_method_id: str,
    billing_country: str | None,
) -> None:
    """Block when CH appears on exactly one of (card issuer country,
    payload billing country).

    `billing_country` is the country from the request payload
    (`payload.billing_address.country`), what the user typed on the
    frontend, not the PaymentMethod's `billing_details` (which can be
    set client-side to anything).
    """
    if not settings.BILLING_BLOCK_CH_COUNTRY_MISMATCH:
        return

    pm = await stripe_service.get_payment_method(payment_method_id)
    card_country = (pm.card.country if pm.card else None) or ""

    card_is_ch = card_country.upper() == "CH"
    billing_is_ch = (billing_country or "").upper() == "CH"

    if card_is_ch != billing_is_ch:
        logger.warning(
            "CH country mismatch block: card_country=%s billing_country=%s "
            "payment_method=%s",
            card_country or "?",
            billing_country or "?",
            payment_method_id,
        )
        raise CountryMismatchBlocked(
            card_country=card_country,
            billing_country=billing_country or "",
        )
