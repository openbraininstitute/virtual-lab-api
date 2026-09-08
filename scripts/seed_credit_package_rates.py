#!/usr/bin/env python3
"""Seed (or reset) credit_package_rate rows for a given currency.

Usage:
    # Dry-run (default): show what would be inserted
    uv run python scripts/seed_credit_package_rates.py

    # Apply: insert/replace the CHF volume discount tiers
    uv run python scripts/seed_credit_package_rates.py --apply

    # Reset to flat pricing (single catch-all row)
    uv run python scripts/seed_credit_package_rates.py --apply --flat

    # Custom currency
    uv run python scripts/seed_credit_package_rates.py --apply --currency usd

Environment:
    DATABASE_URL — async PostgreSQL URL (reads from .env.local by default)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from decimal import Decimal

from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_labs.infrastructure.db.models import CreditPackageRate  # noqa: E402



@dataclass(frozen=True)
class TierDef:
    min_credits: int
    max_credits: int | None
    rate: Decimal
    discount_pct: int


# CHF volume discount schedule (from pricing table)
CHF_VOLUME_TIERS: list[TierDef] = [
    TierDef(min_credits=1, max_credits=499, rate=Decimal("0.100000"), discount_pct=0),
    TierDef(min_credits=500, max_credits=999, rate=Decimal("0.095000"), discount_pct=5),
    TierDef(min_credits=1000, max_credits=4999, rate=Decimal("0.090000"), discount_pct=10),
    TierDef(min_credits=5000, max_credits=9999, rate=Decimal("0.085000"), discount_pct=15),
    TierDef(min_credits=10000, max_credits=24999, rate=Decimal("0.080000"), discount_pct=20),
    TierDef(min_credits=25000, max_credits=49999, rate=Decimal("0.075000"), discount_pct=25),
    TierDef(min_credits=50000, max_credits=None, rate=Decimal("0.070000"), discount_pct=30),
]

# Flat pricing: single catch-all row
CHF_FLAT_TIER: list[TierDef] = [
    TierDef(min_credits=1, max_credits=None, rate=Decimal("0.100000"), discount_pct=0),
]



async def seed_rates(
    database_url: str,
    currency: str,
    tiers: list[TierDef],
    apply: bool,
) -> None:
    engine = create_async_engine(database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            # Show current state
            existing = (
                await session.execute(
                    select(CreditPackageRate)
                    .where(CreditPackageRate.currency == currency)
                    .order_by(CreditPackageRate.min_credits)
                )
            ).scalars().all()

            print(f"\n{'='*60}")
            print(f"  Currency: {currency.upper()}")
            print(f"  Mode: {'APPLY' if apply else 'DRY-RUN'}")
            print(f"{'='*60}")

            if existing:
                print(f"\n  Current rows ({len(existing)}):")
                for row in existing:
                    max_str = str(row.max_credits) if row.max_credits else "∞"
                    active_str = "✓" if row.active else "✗"
                    print(
                        f"    [{active_str}] {row.min_credits:>6} – {max_str:>6}  "
                        f"rate={row.rate}  discount={row.discount_pct}%"
                    )
            else:
                print("\n  No existing rows.")

            print(f"\n  Target rows ({len(tiers)}):")
            for tier in tiers:
                max_str = str(tier.max_credits) if tier.max_credits else "∞"
                print(
                    f"    {tier.min_credits:>6} – {max_str:>6}  "
                    f"rate={tier.rate}  discount={tier.discount_pct}%"
                )

            if not apply:
                print("\n  [DRY-RUN] No changes applied. Pass --apply to write.\n")
                return


            await session.execute(
                update(CreditPackageRate)
                .where(
                    CreditPackageRate.currency == currency,
                    CreditPackageRate.active.is_(True),
                )
                .values(active=False, deactivated_at=datetime.now(timezone.utc))
            )

            # Insert new tiers
            for tier in tiers:
                session.add(
                    CreditPackageRate(
                        currency=currency,
                        min_credits=tier.min_credits,
                        max_credits=tier.max_credits,
                        rate=tier.rate,
                        discount_pct=tier.discount_pct,
                        active=True,
                        activated_at=datetime.now(timezone.utc),
                    )
                )

            await session.commit()
            print(f"\n  ✅ Inserted {len(tiers)} rows for {currency.upper()}.\n")

    finally:
        await engine.dispose()


def main() -> None:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(
        description="Seed credit_package_rate rows for volume-based pricing."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this, only shows the plan.",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Seed a single flat-rate row instead of volume tiers (disables discounts).",
    )
    parser.add_argument(
        "--currency",
        default="chf",
        help="Currency to seed (default: chf).",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL") or os.getenv(
        "DATABASE_URI",
        "postgresql+asyncpg://user:pass@host:port/db_name",
    )
    tiers = CHF_FLAT_TIER if args.flat else CHF_VOLUME_TIERS

    asyncio.run(
        seed_rates(
            database_url=database_url,
            currency=args.currency.lower(),
            tiers=tiers,
            apply=args.apply,
        )
    )


if __name__ == "__main__":
    main()
