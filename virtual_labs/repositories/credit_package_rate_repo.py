"""Repository for credit package rate lookups."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import CreditPackageRate


class CreditPackageRateRepository:
    """Read-only repository for resolving volume-based credit pricing."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_rate_for_credits(
        self, credits: int, currency: str
    ) -> Optional[CreditPackageRate]:
        """Find the active pricing tier that covers the given credit count.

        The query matches the single row where:
        - currency matches
        - active is true
        - min_credits <= credits
        - max_credits >= credits OR max_credits IS NULL (catch-all)

        Returns None if no matching tier exists (should not happen if
        the DB is seeded correctly with at least one catch-all row).
        """
        stmt = (
            select(CreditPackageRate)
            .where(
                and_(
                    CreditPackageRate.currency == currency.lower(),
                    CreditPackageRate.active.is_(True),
                    CreditPackageRate.min_credits <= credits,
                    (CreditPackageRate.max_credits >= credits)
                    | (CreditPackageRate.max_credits.is_(None)),
                )
            )
            .order_by(CreditPackageRate.min_credits.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_base_rate(self, currency: str) -> Optional[Decimal]:
        """Get the rate for the smallest tier (min_credits=1).

        Used for reverse calculations (currency → credits) and to
        provide a `base_rate` reference for discount display.
        """
        stmt = (
            select(CreditPackageRate.rate)
            .where(
                and_(
                    CreditPackageRate.currency == currency.lower(),
                    CreditPackageRate.active.is_(True),
                )
            )
            .order_by(CreditPackageRate.min_credits.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_all_active_rates(self, currency: str) -> list[CreditPackageRate]:
        """Return all active tiers for a currency, ordered by min_credits.

        Used by the GET /billing/credit-package-rates endpoint to render
        the full pricing table for the frontend.
        """
        stmt = (
            select(CreditPackageRate)
            .where(
                and_(
                    CreditPackageRate.currency == currency.lower(),
                    CreditPackageRate.active.is_(True),
                )
            )
            .order_by(CreditPackageRate.min_credits.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
