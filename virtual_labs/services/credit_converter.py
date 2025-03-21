from decimal import Decimal
from typing import Dict, Optional, Union

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.repositories.credit_exchange_rate_repo import (
    CreditExchangeRateQueryRepository as ExchangeRateQueryRepository,
)

# Default exchange rates for fallback
DEFAULT_EXCHANGE_RATES = {
    "chf": Decimal("0.05"),
    "usd": Decimal("0.055"),
    "eur": Decimal("0.048"),
}


class CreditConverter:
    """Utility for converting between credits and currency amount (in cents) using database rates."""

    def __init__(self, exchange_rate_repo: ExchangeRateQueryRepository):
        """
        Initialize the converter with a repository.

        Args:
            exchange_rate_repo: Repository for accessing exchange rates
        """
        self.exchange_rate_repo = exchange_rate_repo
        self._cached_rates: Optional[Dict[str, Decimal]] = None

    async def _ensure_rates_loaded(self) -> Dict[str, Decimal]:
        """Ensure exchange rates are loaded from the database."""
        if self._cached_rates is None:
            self._cached_rates = await self.exchange_rate_repo.get_all_rates()
            # If no rates found in DB, use defaults
            if not self._cached_rates:
                self._cached_rates = DEFAULT_EXCHANGE_RATES
        return self._cached_rates

    async def currency_to_credits(
        self, amount: Union[Decimal, int, str], currency: str
    ) -> Decimal:
        """Convert a currency amount (in cents) to credits."""
        currency = currency.lower()
        rates = await self._ensure_rates_loaded()

        if currency not in rates:
            raise ValueError(f"Unsupported currency: {currency}")

        amount_decimal = (
            Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
        )
        return amount_decimal / rates[currency] / Decimal("100")

    async def credits_to_currency(
        self, credits: Union[Decimal, int, str], currency: str
    ) -> Decimal:
        """Convert credits to a currency amount."""
        currency = currency.lower()
        rates = await self._ensure_rates_loaded()

        if currency not in rates:
            raise ValueError(f"Unsupported currency: {currency}")

        credits_decimal = (
            Decimal(str(credits)) if not isinstance(credits, Decimal) else credits
        )
        return credits_decimal * rates[currency] * Decimal("100")

    async def get_exchange_rate(self, currency: str) -> Decimal:
        """Get the exchange rate for a currency."""
        currency = currency.lower()
        rates = await self._ensure_rates_loaded()

        if currency not in rates:
            raise ValueError(f"Unsupported currency: {currency}")

        return rates[currency]

    async def refresh_rates(self) -> None:
        """Force refresh of exchange rates from the database."""
        self._cached_rates = None
        await self._ensure_rates_loaded()


async def get_exchange_rate_repo(
    session: AsyncSession = Depends(default_session_factory),
) -> ExchangeRateQueryRepository:
    return ExchangeRateQueryRepository(session=session)


async def get_credit_converter(
    repo: ExchangeRateQueryRepository = Depends(get_exchange_rate_repo),
) -> CreditConverter:
    return CreditConverter(exchange_rate_repo=repo)
