from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import CreditExchangeRate as ExchangeRate


class CreditExchangeRateQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_rates(self) -> Dict[str, Decimal]:
        """Retrieve all exchange rates from the database."""
        query = select(ExchangeRate)
        result = await self.session.execute(statement=query)
        rates = result.scalars().all()
        return {rate.currency.lower(): rate.rate for rate in rates}

    async def get_rate(self, currency: str) -> Optional[Decimal]:
        """Get exchange rate for a specific currency."""
        query = select(ExchangeRate).where(ExchangeRate.currency == currency.lower())
        result = await self.session.execute(statement=query)
        rate = result.scalar_one_or_none()
        return rate.rate if rate else None


class CreditExchangeRateMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_or_update_rate(
        self, currency: str, rate: Decimal, description: Optional[str] = None
    ) -> ExchangeRate:
        """Add or update an exchange rate."""
        currency = currency.lower()

        # Check if rate exists
        query = select(ExchangeRate).where(ExchangeRate.currency == currency)
        existing = await self.session.execute(statement=query)
        rate_obj = existing.scalar_one_or_none()

        if rate_obj:
            # Update existing rate
            stmt = (
                update(ExchangeRate)
                .where(ExchangeRate.currency == currency)
                .values(rate=rate, description=description)
            )
            await self.session.execute(stmt)
        else:
            # Create new rate
            rate_obj = ExchangeRate(
                currency=currency, rate=rate, description=description
            )
            self.session.add(rate_obj)

        await self.session.commit()
        await self.session.refresh(rate_obj)
        return rate_obj

    async def bulk_upsert_rates(self, rates: Dict[str, Decimal]) -> None:
        """Bulk update or insert multiple exchange rates."""
        for currency, rate in rates.items():
            await self.add_or_update_rate(currency.lower(), rate)
