#!/usr/bin/env python3
"""
Virtual Lab manager — interactive read-only inspector.

Displays detailed information about a virtual lab including its
projects, users (from DB relationships), subscriptions, payments,
invites, and promotion code usage.

Usage
-----
  # Interactive menu (select what to view)
  uv run python scripts/vlab_manager.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001

  # Show everything at once
  uv run python scripts/vlab_manager.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --all

  # Show specific sections
  uv run python scripts/vlab_manager.py \
      --virtual-lab-id ... --projects --subscriptions

Environment
-----------
  DATABASE_URL — async PostgreSQL URL (reads from .env.local by default)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime

from dotenv import load_dotenv
from InquirerPy import inquirer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_labs.infrastructure.db.models import (  # noqa: E402
    PaymentMethod,
    Project,
    PromotionCode,
    PromotionCodeUsage,
    Subscription,
    SubscriptionPayment,
    VirtualLab,
    VirtualLabInvite,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

console = Console()
logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    database_url: str
    virtual_lab_id: uuid.UUID
    show_projects: bool
    show_users: bool
    show_subscriptions: bool
    show_payments: bool
    show_invites: bool
    show_promotions: bool

    @property
    def show_all(self) -> bool:
        return all(
            [
                self.show_projects,
                self.show_users,
                self.show_subscriptions,
                self.show_payments,
                self.show_invites,
                self.show_promotions,
            ]
        )


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _banner(title: str, body: str = "", style: str = "bright_blue") -> None:
    console.print(
        Panel(f"[bold]{title}[/]\n{body}".strip(), border_style=style, padding=(1, 2))
    )


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_bool(val: bool | None) -> str:
    if val is None:
        return "—"
    return "✓" if val else "✗"


def _fmt_cents(cents: int | None, currency: str = "CHF") -> str:
    if cents is None:
        return "—"
    return f"{cents / 100:.2f} {currency.upper()}"


# ---------------------------------------------------------------------------
# Display: Virtual Lab Overview
# ---------------------------------------------------------------------------


async def show_overview(session: AsyncSession, vl: VirtualLab) -> None:
    _banner("Virtual Lab Overview")

    table = Table(show_header=False, padding=(0, 1))
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("ID", str(vl.id))
    table.add_row("Name", vl.name)
    table.add_row("Description", vl.description or "—")
    table.add_row("Entity", vl.entity)
    table.add_row("Email", vl.reference_email or "—")
    table.add_row("Email verified", _fmt_bool(vl.email_verified))
    table.add_row(
        "Compute cell", str(vl.compute_cell.value) if vl.compute_cell else "—"
    )
    table.add_row("Owner ID", str(vl.owner_id))
    table.add_row("Admin group", vl.admin_group_id)
    table.add_row("Member group", vl.member_group_id)
    table.add_row("Deleted", _fmt_bool(vl.deleted))
    table.add_row("Created", _fmt_dt(vl.created_at))
    table.add_row("Updated", _fmt_dt(vl.updated_at))
    console.print(table)


# ---------------------------------------------------------------------------
# Display: Projects
# ---------------------------------------------------------------------------


async def show_projects(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner("Projects")

    projects = (
        (
            await session.execute(
                select(Project)
                .where(Project.virtual_lab_id == vl_id)
                .order_by(Project.created_at)
            )
        )
        .scalars()
        .all()
    )

    if not projects:
        console.print("  [dim]No projects found.[/]")
        return

    table = Table(header_style="bold cyan", padding=(0, 1))
    for col in ("ID", "Name", "Deleted", "Owner", "Created"):
        table.add_column(col)

    for p in projects:
        table.add_row(
            str(p.id),
            p.name,
            _fmt_bool(p.deleted),
            str(p.owner_id),
            _fmt_dt(p.created_at),
        )

    console.print(table)
    console.print(f"  [dim]Total: {len(projects)}[/]")


# ---------------------------------------------------------------------------
# Display: Users (from DB relationships — subscriptions, project owners)
# ---------------------------------------------------------------------------


async def show_users(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner(
        "Users",
        "Users derived from DB relationships (project owners, subscribers, invitees).\n"
        "Full membership is managed in Keycloak groups.",
    )

    # Collect user IDs from multiple sources
    user_sources: dict[uuid.UUID, set[str]] = {}

    def _add(uid: uuid.UUID, source: str) -> None:
        user_sources.setdefault(uid, set()).add(source)

    # VL owner
    vl = (
        await session.execute(select(VirtualLab).where(VirtualLab.id == vl_id))
    ).scalar_one()
    _add(vl.owner_id, "vl_owner")

    # Project owners
    project_owners = (
        (
            await session.execute(
                select(Project.owner_id)
                .where(and_(Project.virtual_lab_id == vl_id, ~Project.deleted))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    for uid in project_owners:
        _add(uid, "project_owner")

    # Subscribers
    subscribers = (
        (
            await session.execute(
                select(Subscription.user_id)
                .where(Subscription.virtual_lab_id == vl_id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    for uid in subscribers:
        _add(uid, "subscriber")

    # Invitees (accepted)
    accepted_invites = (
        (
            await session.execute(
                select(VirtualLabInvite.user_id)
                .where(
                    and_(
                        VirtualLabInvite.virtual_lab_id == vl_id,
                        VirtualLabInvite.accepted.is_(True),
                        VirtualLabInvite.user_id.isnot(None),
                    )
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    for uid in accepted_invites:
        if uid is not None:
            _add(uid, "invite_accepted")

    if not user_sources:
        console.print("  [dim]No users found.[/]")
        return

    table = Table(header_style="bold cyan", padding=(0, 1))
    table.add_column("User ID")
    table.add_column("Roles / Sources")

    for uid, sources in sorted(user_sources.items(), key=lambda x: str(x[0])):
        table.add_row(str(uid), ", ".join(sorted(sources)))

    console.print(table)
    console.print(f"  [dim]Total unique users: {len(user_sources)}[/]")


# ---------------------------------------------------------------------------
# Display: Subscriptions
# ---------------------------------------------------------------------------


async def show_subscriptions(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner("Subscriptions")

    subs = (
        (
            await session.execute(
                select(Subscription)
                .where(Subscription.virtual_lab_id == vl_id)
                .order_by(Subscription.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    if not subs:
        console.print("  [dim]No subscriptions found.[/]")
        return

    table = Table(header_style="bold cyan", padding=(0, 1))
    for col in ("ID", "Type", "Status", "User", "Period start", "Period end", "Source"):
        table.add_column(col)

    for s in subs:
        table.add_row(
            str(s.id)[:8] + "…",
            s.subscription_type or s.type or "—",
            str(s.status.value) if s.status else "—",
            str(s.user_id)[:8] + "…",
            _fmt_dt(s.current_period_start),
            _fmt_dt(s.current_period_end),
            str(s.source.value) if s.source else "—",
        )

    console.print(table)
    console.print(f"  [dim]Total: {len(subs)}[/]")


# ---------------------------------------------------------------------------
# Display: Payments
# ---------------------------------------------------------------------------


async def show_payments(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner("Payments")

    payments = (
        (
            await session.execute(
                select(SubscriptionPayment)
                .where(SubscriptionPayment.virtual_lab_id == vl_id)
                .order_by(SubscriptionPayment.payment_date.desc())
            )
        )
        .scalars()
        .all()
    )

    # Also show payment methods
    methods = (
        (
            await session.execute(
                select(PaymentMethod).where(PaymentMethod.virtual_lab_id == vl_id)
            )
        )
        .scalars()
        .all()
    )

    if methods:
        console.print("\n  [bold]Payment Methods:[/]")
        pm_table = Table(header_style="bold cyan", padding=(0, 1))
        for col in ("ID", "Brand", "Last 4", "Cardholder", "Default", "Expires"):
            pm_table.add_column(col)

        for m in methods:
            pm_table.add_row(
                str(m.id)[:8] + "…",
                m.brand,
                m.card_number,
                m.cardholder_name,
                _fmt_bool(m.default),
                m.expire_at or "—",
            )
        console.print(pm_table)

    if not payments:
        console.print("  [dim]No payments found.[/]")
        return

    console.print("\n  [bold]Payment History:[/]")
    table = Table(header_style="bold cyan", padding=(0, 1))
    for col in ("Date", "Amount", "Status", "Card", "Invoice", "Standalone"):
        table.add_column(col)

    for p in payments:
        table.add_row(
            _fmt_dt(p.payment_date),
            _fmt_cents(p.amount_paid, p.currency),
            str(p.status.value) if p.status else "—",
            f"{p.card_brand} •{p.card_last4}",
            p.stripe_invoice_id or "—",
            _fmt_bool(p.standalone),
        )

    console.print(table)
    console.print(f"  [dim]Total payments: {len(payments)}[/]")


# ---------------------------------------------------------------------------
# Display: Invites
# ---------------------------------------------------------------------------


async def show_invites(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner("Invites")

    invites = (
        (
            await session.execute(
                select(VirtualLabInvite)
                .where(VirtualLabInvite.virtual_lab_id == vl_id)
                .order_by(VirtualLabInvite.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    if not invites:
        console.print("  [dim]No invites found.[/]")
        return

    table = Table(header_style="bold cyan", padding=(0, 1))
    for col in ("Email", "Role", "Accepted", "Inviter", "User ID", "Created"):
        table.add_column(col)

    for inv in invites:
        table.add_row(
            inv.user_email,
            inv.role,
            _fmt_bool(inv.accepted),
            str(inv.inviter_id)[:8] + "…",
            str(inv.user_id)[:8] + "…" if inv.user_id else "—",
            _fmt_dt(inv.created_at),
        )

    console.print(table)

    # Summary counts
    total = len(invites)
    accepted = sum(1 for i in invites if i.accepted is True)
    pending = sum(1 for i in invites if i.accepted is None or i.accepted is False)
    console.print(
        f"  [dim]Total: {total} | Accepted: {accepted} | Pending: {pending}[/]"
    )


# ---------------------------------------------------------------------------
# Display: Promotion Codes
# ---------------------------------------------------------------------------


async def show_promotions(session: AsyncSession, vl_id: uuid.UUID) -> None:
    _banner("Promotion Codes & Usage")

    # Show promotion code usages for this VL
    usages = (
        await session.execute(
            select(PromotionCodeUsage, PromotionCode)
            .join(
                PromotionCode, PromotionCodeUsage.promotion_code_id == PromotionCode.id
            )
            .where(PromotionCodeUsage.virtual_lab_id == vl_id)
            .order_by(PromotionCodeUsage.redeemed_at.desc())
        )
    ).all()

    if not usages:
        console.print("  [dim]No promotion code usage found for this virtual lab.[/]")
    else:
        table = Table(header_style="bold cyan", padding=(0, 1))
        for col in ("Code", "Credits", "User", "Status", "Redeemed at"):
            table.add_column(col)

        for usage_row in usages:
            usage, promo = usage_row.tuple()
            table.add_row(
                promo.code,
                str(usage.credits_granted),
                str(usage.user_id)[:8] + "…",
                str(usage.status.value) if usage.status else "—",
                _fmt_dt(usage.redeemed_at),
            )

        console.print(table)
        console.print(f"  [dim]Total usages for this VL: {len(usages)}[/]")

    # Also show all available active promo codes (global, not VL-specific)
    console.print("\n  [bold]All active promotion codes (global):[/]")
    active_promos = (
        (
            await session.execute(
                select(PromotionCode)
                .where(PromotionCode.active.is_(True))
                .order_by(PromotionCode.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )

    if not active_promos:
        console.print("  [dim]No active promotion codes.[/]")
        return

    promo_table = Table(header_style="bold cyan", padding=(0, 1))
    for col in ("Code", "Credits", "Max uses", "Used", "Valid from", "Valid until"):
        promo_table.add_column(col)

    for pc in active_promos:
        promo_table.add_row(
            pc.code,
            str(int(pc.credits_amount)),
            str(pc.max_total_uses) if pc.max_total_uses else "∞",
            str(pc.current_total_uses),
            _fmt_dt(pc.valid_from),
            _fmt_dt(pc.valid_until),
        )

    console.print(promo_table)


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

SECTION_CHOICES = [
    {"name": "Projects", "value": "projects"},
    {"name": "Users", "value": "users"},
    {"name": "Subscriptions", "value": "subscriptions"},
    {"name": "Payments & Payment Methods", "value": "payments"},
    {"name": "Invites", "value": "invites"},
    {"name": "Promotion Codes", "value": "promotions"},
    {"name": "— Show all —", "value": "all"},
    {"name": "— Exit —", "value": "exit"},
]


async def _run_section(section: str, session: AsyncSession, vl_id: uuid.UUID) -> None:
    match section:
        case "projects":
            await show_projects(session, vl_id)
        case "users":
            await show_users(session, vl_id)
        case "subscriptions":
            await show_subscriptions(session, vl_id)
        case "payments":
            await show_payments(session, vl_id)
        case "invites":
            await show_invites(session, vl_id)
        case "promotions":
            await show_promotions(session, vl_id)


async def _run_all(session: AsyncSession, vl_id: uuid.UUID) -> None:
    for section in (
        "projects",
        "users",
        "subscriptions",
        "payments",
        "invites",
        "promotions",
    ):
        await _run_section(section, session, vl_id)
        console.print()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _parse_args() -> RunConfig:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(
        description="Interactive virtual lab manager — inspect lab data."
    )
    parser.add_argument(
        "--virtual-lab-id",
        required=True,
        help="UUID of the virtual lab to inspect.",
    )
    parser.add_argument("--all", action="store_true", help="Show all sections at once.")
    parser.add_argument("--projects", action="store_true", help="Show projects.")
    parser.add_argument("--users", action="store_true", help="Show users.")
    parser.add_argument(
        "--subscriptions", action="store_true", help="Show subscriptions."
    )
    parser.add_argument("--payments", action="store_true", help="Show payments.")
    parser.add_argument("--invites", action="store_true", help="Show invites.")
    parser.add_argument(
        "--promotions", action="store_true", help="Show promotion codes."
    )
    args = parser.parse_args()

    try:
        virtual_lab_id = uuid.UUID(args.virtual_lab_id)
    except ValueError:
        logger.error(f"Invalid virtual-lab-id: '{args.virtual_lab_id}'")
        raise SystemExit(2)

    # If --all or no specific section flags, we'll use interactive mode
    if args.all:
        pass  # all flags already set above via `args.all or args.X`

    database_url = os.getenv("DATABASE_URL") or os.getenv(
        "DATABASE_URI",
        "postgresql+asyncpg://user:pass@host:port/db_name",
    )

    return RunConfig(
        database_url=database_url,
        virtual_lab_id=virtual_lab_id,
        show_projects=args.all or args.projects,
        show_users=args.all or args.users,
        show_subscriptions=args.all or args.subscriptions,
        show_payments=args.all or args.payments,
        show_invites=args.all or args.invites,
        show_promotions=args.all or args.promotions,
    )


async def _amain(cfg: RunConfig) -> int:
    engine = create_async_engine(cfg.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            # Validate VL exists
            vl = (
                await session.execute(
                    select(VirtualLab).where(VirtualLab.id == cfg.virtual_lab_id)
                )
            ).scalar_one_or_none()

            if vl is None:
                logger.error(f"❌ Virtual lab {cfg.virtual_lab_id} not found.")
                return 2

            await show_overview(session, vl)

            # If specific sections requested via CLI flags, show them
            if cfg.show_all:
                await _run_all(session, cfg.virtual_lab_id)
                return 0

            any_flag = any(
                [
                    cfg.show_projects,
                    cfg.show_users,
                    cfg.show_subscriptions,
                    cfg.show_payments,
                    cfg.show_invites,
                    cfg.show_promotions,
                ]
            )

            if any_flag:
                if cfg.show_projects:
                    await show_projects(session, cfg.virtual_lab_id)
                if cfg.show_users:
                    await show_users(session, cfg.virtual_lab_id)
                if cfg.show_subscriptions:
                    await show_subscriptions(session, cfg.virtual_lab_id)
                if cfg.show_payments:
                    await show_payments(session, cfg.virtual_lab_id)
                if cfg.show_invites:
                    await show_invites(session, cfg.virtual_lab_id)
                if cfg.show_promotions:
                    await show_promotions(session, cfg.virtual_lab_id)
                return 0

            # Interactive mode — loop until user exits
            while True:
                choice = await inquirer.select(
                    message="What would you like to view?",
                    choices=SECTION_CHOICES,
                    default="projects",
                ).execute_async()

                if choice == "exit":
                    break
                elif choice == "all":
                    await _run_all(session, cfg.virtual_lab_id)
                else:
                    await _run_section(choice, session, cfg.virtual_lab_id)

                console.print()

    finally:
        await engine.dispose()

    return 0


def run() -> int:
    cfg = _parse_args()
    return asyncio.run(_amain(cfg))


if __name__ == "__main__":
    sys.exit(run())
