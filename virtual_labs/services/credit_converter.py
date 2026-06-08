"""Credit-to-currency conversion using volume-based pricing.

Resolves the unit price per credit from the `credit_package_rate` table.
A single catch-all row (min=1, max=NULL) reproduces flat pricing;
multiple rows with non-overlapping ranges provide volume discounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.repositories.credit_package_rate_repo import (
    CreditPackageRateRepository,
)


@dataclass(frozen=True, slots=True)
class CreditConversionResult:
    """Result of a credit-to-currency conversion."""

    amount: int  # total in smallest currency unit (cents/rappen)
    rate: Decimal  # effective rate per credit
    discount_pct: int  # 0 when flat, 5/10/15… for volume tiers
    base_rate: Decimal  # rate for the smallest tier (for "Save X%" display)
    credit_package_rate_id: UUID | None  # FK to credit_package_rate row used


class CreditConverter:
    """Converts between credits and currency amounts using volume-based pricing."""

    def __init__(self, package_rate_repo: CreditPackageRateRepository) -> None:
        self.package_rate_repo = package_rate_repo

    async def credits_to_currency(self, credits: int, currency: str) -> Decimal:
        """Convert credits to a currency amount (in smallest unit, e.g. cents).

        Backward-compatible signature: returns just the amount as a Decimal.
        Use `convert_credits` for the full breakdown.
        """
        result = await self.convert_credits(credits, currency)
        return Decimal(str(result.amount))

    async def convert_credits(
        self, credits: int, currency: str
    ) -> CreditConversionResult:
        """Convert credits to currency with full tier breakdown.

        Raises ValueError if no matching tier is found for the currency.
        """
        currency = currency.lower()
        tier = await self.package_rate_repo.get_rate_for_credits(credits, currency)
        if tier is None:
            raise ValueError(
                f"No pricing tier found for {credits} credits in {currency}"
            )

        amount = int(Decimal(str(credits)) * tier.rate * Decimal("100"))
        base_rate = await self.package_rate_repo.get_base_rate(currency)

        return CreditConversionResult(
            amount=amount,
            rate=tier.rate,
            discount_pct=tier.discount_pct,
            base_rate=base_rate or tier.rate,
            credit_package_rate_id=tier.id,
        )

    async def currency_to_credits(self, amount: int, currency: str) -> Decimal:
        """Convert a currency amount (in cents) to credits using the base rate.

        This is approximate / display-only. The authoritative direction
        is always credits → currency (via volume tier lookup).
        """
        currency = currency.lower()
        base_rate = await self.package_rate_repo.get_base_rate(currency)
        if base_rate is None:
            raise ValueError(f"Unsupported currency: {currency}")

        return Decimal(str(amount)) / base_rate / Decimal("100")

    async def get_exchange_rate(self, currency: str) -> Decimal:
        """Get the base exchange rate for a currency.

        Backward-compatible: returns the rate for the lowest tier.
        """
        currency = currency.lower()
        base_rate = await self.package_rate_repo.get_base_rate(currency)
        if base_rate is None:
            raise ValueError(f"Unsupported currency: {currency}")
        return base_rate


async def get_credit_converter(
    session: AsyncSession = Depends(default_session_factory),
) -> CreditConverter:
    return CreditConverter(
        package_rate_repo=CreditPackageRateRepository(session=session),
    )
