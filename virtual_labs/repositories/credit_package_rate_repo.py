"""Repository for credit package rate lookups."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
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
        """Get the list price: the rate of the ``min_credits = 1`` tier.

        Used for reverse calculations (currency → credits) and as the
        `base_rate` reference for discount display. The contract is the
        *list price*, so this pins ``min_credits = 1`` rather than "the
        lowest active tier" — otherwise a currency seeded without a base
        row would silently report a discounted tier as the list price,
        corrupting "Save X%" display and reverse conversions.

        Returns None if the currency has no active ``min_credits = 1`` row.
        """
        stmt = (
            select(CreditPackageRate.rate)
            .where(
                and_(
                    CreditPackageRate.currency == currency.lower(),
                    CreditPackageRate.active.is_(True),
                    CreditPackageRate.min_credits == 1,
                )
            )
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

    async def get_all_rates(
        self, currency: Optional[str] = None
    ) -> list[CreditPackageRate]:
        """All rates — active and inactive — for the platform-admin
        namespace, optionally narrowed to one currency."""
        stmt = select(CreditPackageRate).order_by(
            CreditPackageRate.currency.asc(), CreditPackageRate.min_credits.asc()
        )
        if currency:
            stmt = stmt.where(CreditPackageRate.currency == currency.lower())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_rate_by_id(self, rate_id: UUID) -> Optional[CreditPackageRate]:
        return await self.session.get(CreditPackageRate, rate_id)

    async def count_active_range_conflicts(
        self, *, currency: str, min_credits: int, exclude_rate_id: UUID
    ) -> int:
        """Active rows colliding with the `uq_credit_package_rate_currency_min`
        partial unique index, so an activation can be pre-checked."""
        count = await self.session.scalar(
            select(func.count(CreditPackageRate.id)).where(
                and_(
                    CreditPackageRate.currency == currency.lower(),
                    CreditPackageRate.min_credits == min_credits,
                    CreditPackageRate.active.is_(True),
                    CreditPackageRate.id != exclude_rate_id,
                )
            )
        )
        return count or 0


class CreditPackageRateMutationRepository:
    """Write access to credit package rates (platform-admin only)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def update_rate(
        self, rate: CreditPackageRate, fields: dict[str, object]
    ) -> CreditPackageRate:
        """Apply the given field values to a rate row and persist.
        Stamps `activated_at`/`deactivated_at` on `active` flips."""
        if "active" in fields and bool(fields["active"]) != rate.active:
            if fields["active"]:
                fields = {**fields, "activated_at": func.now(), "deactivated_at": None}
            else:
                fields = {**fields, "deactivated_at": func.now()}
        for key, value in fields.items():
            setattr(rate, key, value)
        await self.session.commit()
        await self.session.refresh(rate)
        return rate
