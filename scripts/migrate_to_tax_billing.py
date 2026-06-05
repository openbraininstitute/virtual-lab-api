#!/usr/bin/env python3
"""
Tax-billing migration runner.

Companion to scripts/MIGRATE_TO_TAX.md — see that file for the full
plan, decision matrix, and rollback notes.

What this script does
---------------------
Migrates a deployment from "single product / two prices / no tax"
to the tax-aware billing model introduced by this PR. Walks through
seven phases (preflight, audit, product tax_code, prices, customer
addresses, active subscriptions, DB reconciliation, summary), each
gated on a `Proceed?` confirmation, all writes hidden behind
`--apply`. Without `--apply` it is strictly read-only.

Usage
-----
  poetry run migrate-tax-billing --product-id prod_XXX            # audit only
  poetry run migrate-tax-billing --product-id prod_XXX \\
      --tax-code txcd_10103000 --tax-countries CH,DE \\
      --address-policy mark_for_followup                           # full plan, dry-run
  poetry run migrate-tax-billing ... --apply                       # writes

Active subscriptions are always swapped at end-of-period (no
proration); old prices are always cloned (Stripe locks
`tax_behavior` once written, so patching is unreliable). Both are
deliberate single-policy choices — see scripts/MIGRATE_TO_TAX.md
for the rationale.

Add to pyproject.toml [tool.poetry.scripts]:
    migrate-tax-billing = "scripts.migrate_to_tax_billing:run"

The runner can abort at any phase boundary; each phase is
idempotent and re-running picks up where you stopped. Every action
that changes Stripe or the DB is dumped into ./migration-out/
(JSON/CSV) for audit.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, cast

import stripe
from dotenv import load_dotenv
from InquirerPy import inquirer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Lazy-import the project so the script can also be used in a
# detached context (e.g. ops VM) by setting DATABASE_URL alone.
from virtual_labs.infrastructure.db.models import (
    StripeUser,
    SubscriptionTier,
)

# ---------------------------------------------------------------------------
# Constants & globals
# ---------------------------------------------------------------------------

console = Console()
logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)

OUT_DIR = Path("migration-out")
OUT_DIR.mkdir(exist_ok=True)
RUN_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# Active subscriptions are always migrated at the end of the current
# billing period: no proration, no mid-cycle invoice surprises, and
# the existing `customer.subscription.updated` webhook reconciles the
# local row when the swap actually fires. This is a deliberate
# single-policy choice — see scripts/MIGRATE_TO_TAX.md for the
# trade-offs we considered.
AddressPolicy = Literal["mark_for_followup", "attempt_keycloak_sync"]


# ---------------------------------------------------------------------------
# Run config
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """All migration knobs in one place — printed back to the runner
    in Phase 0 so they can audit before any write happens."""

    stripe_api_key: str
    database_url: str
    product_id: str
    tax_code: Optional[str]
    tax_countries: list[str]
    address_policy: AddressPolicy
    apply: bool

    @property
    def dry_run(self) -> bool:
        return not self.apply


# State shared across phases — populated as we go, snapshotted at
# the end into migration-summary-<ts>.json.
@dataclass
class MigrationState:
    audit_before: dict[str, Any] = field(default_factory=dict)
    audit_after: dict[str, Any] = field(default_factory=dict)
    product_tax_code_changed: bool = False
    price_actions: list[dict[str, Any]] = field(default_factory=list)
    price_clone_map: dict[str, str] = field(default_factory=dict)  # old → new
    customer_actions: list[dict[str, Any]] = field(default_factory=list)
    customers_no_address: list[dict[str, Any]] = field(default_factory=list)
    subscription_actions: list[dict[str, Any]] = field(default_factory=list)
    db_actions: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------


def _banner(title: str, body: str = "", style: str = "bright_blue") -> None:
    console.print(
        Panel(f"[bold]{title}[/]\n{body}".strip(), border_style=style, padding=(1, 2))
    )


def _safe(val: Optional[str], max_len: int = 0) -> str:
    if not val:
        return "—"
    if max_len and len(val) > max_len:
        return val[: max_len - 1] + "…"
    return val


async def _confirm_phase(name: str, dry_run: bool) -> Literal["yes", "skip", "abort"]:
    suffix = "[DRY-RUN]" if dry_run else "[WILL WRITE]"
    return cast(
        Literal["yes", "skip", "abort"],
        await inquirer.select(
            message=f"{suffix} Proceed with {name}?",
            choices=[
                {"name": "yes — execute this phase", "value": "yes"},
                {"name": "skip — move to the next phase", "value": "skip"},
                {"name": "abort — stop the migration here", "value": "abort"},
            ],
            default="yes",
        ).execute_async(),
    )


def _dump(name: str, payload: Any) -> Path:
    """Write a JSON artefact under migration-out/. Returns the path."""
    path = OUT_DIR / f"{name}-{RUN_TS}.json"
    path.write_text(json.dumps(payload, default=str, indent=2))
    logger.info(f"   ↳ wrote {path}")
    return path


def _dump_csv(name: str, rows: list[dict[str, Any]]) -> Path:
    path = OUT_DIR / f"{name}-{RUN_TS}.csv"
    if not rows:
        path.write_text("")
        return path
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"   ↳ wrote {path}")
    return path


# ---------------------------------------------------------------------------
# Stripe & DB clients
# ---------------------------------------------------------------------------


def _stripe(api_key: str) -> stripe.StripeClient:
    return stripe.StripeClient(api_key=api_key)


def _db_engine(database_url: str):
    # echo=False to avoid drowning the operator in SQL; switch on for debug.
    return create_async_engine(database_url, echo=False)


# ---------------------------------------------------------------------------
# Phase 0 — Preflight
# ---------------------------------------------------------------------------


async def phase0_preflight(cfg: RunConfig) -> None:
    _banner("Phase 0 — Preflight", "Validate environment + connectivity. No writes.")

    table = Table(show_header=False, padding=(0, 1))
    table.add_column("Setting", style="bold")
    table.add_column("Value")
    table.add_row(
        "Mode", "[red]APPLY (will write)[/]" if cfg.apply else "[green]DRY-RUN[/]"
    )
    table.add_row("Database URL", _safe(cfg.database_url, 80))
    table.add_row("Stripe key prefix", cfg.stripe_api_key[:8] + "…")
    table.add_row("Product ID", cfg.product_id)
    table.add_row(
        "Tax code", cfg.tax_code or "[yellow](unset — Phase 2 will be skipped)[/]"
    )
    table.add_row("Tax countries", ",".join(cfg.tax_countries) or "[yellow](unset)[/]")
    table.add_row("Swap policy", "at_period_end (fixed)")
    table.add_row("Address policy", cfg.address_policy)
    console.print(table)

    # Stripe reachability
    try:
        client = _stripe(cfg.stripe_api_key)
        balance = client.balance.retrieve()
        logger.info(f"✅ Stripe reachable; livemode={balance.livemode}")
    except stripe.AuthenticationError:
        logger.error("❌ Stripe auth failed. Check STRIPE_SECRET_KEY.")
        raise SystemExit(2)
    except Exception as e:
        logger.error(f"❌ Stripe unreachable: {e}")
        raise SystemExit(2)

    # DB reachability
    print("@@@cfg.database_url", cfg.database_url)
    engine = _db_engine(cfg.database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        logger.info("✅ DB reachable")
    except Exception as e:
        logger.error(f"❌ DB unreachable: {e}")
        raise SystemExit(2)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Phase 1 — Audit
# ---------------------------------------------------------------------------


async def phase1_audit(cfg: RunConfig, state: MigrationState) -> dict[str, Any]:
    _banner("Phase 1 — Audit", "Read-only inventory of Stripe + DB.")

    client = _stripe(cfg.stripe_api_key)

    # Product + prices
    product = client.products.retrieve(cfg.product_id)
    prices = list(
        client.prices.list(
            params={"product": cfg.product_id, "limit": 100}
        ).auto_paging_iter()
    )

    prices_table = Table(
        title=f"Prices on {product.id}", header_style="bold cyan", padding=(0, 1)
    )
    for col in ("Price ID", "Interval", "Amount", "Currency", "tax_behavior", "Active"):
        prices_table.add_column(col)
    for p in prices:
        rec = p.get("recurring") or {}
        prices_table.add_row(
            p.id,
            rec.get("interval", "—"),
            f"{(p.unit_amount or 0) / 100:.2f}",
            (p.currency or "").upper(),
            p.get("tax_behavior") or "unspecified",
            "yes" if p.active else "no",
        )
    console.print(prices_table)

    # Customers — count + address coverage
    customers_total = 0
    customers_with_country = 0
    countries: dict[str, int] = {}
    for c in client.customers.list(params={"limit": 100}).auto_paging_iter():
        customers_total += 1
        country = (c.address or {}).get("country") if c.address else None
        if country:
            customers_with_country += 1
            countries[country] = countries.get(country, 0) + 1

    # Subscriptions
    subs_total = 0
    subs_active = 0
    subs_with_auto_tax = 0
    subs_by_price: dict[str, int] = {}
    for sub in client.subscriptions.list(
        params={"status": "all", "limit": 100, "expand": ["data.items.data.price"]}
    ).auto_paging_iter():
        subs_total += 1
        if sub.status in ("active", "trialing"):
            subs_active += 1
        at = (sub.get("automatic_tax") or {}).get("enabled")
        if at:
            subs_with_auto_tax += 1
        items = (sub.get("items") or {}).get("data") or []
        for it in items:
            price_id = (it.get("price") or {}).get("id")
            if price_id:
                subs_by_price[price_id] = subs_by_price.get(price_id, 0) + 1

    # DB tier rows
    engine = _db_engine(cfg.database_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    tier_rows: list[dict[str, Any]] = []
    try:
        async with Session() as session:
            res = await session.execute(select(SubscriptionTier))
            for t in res.scalars().all():
                tier_rows.append(
                    {
                        "id": str(t.id),
                        "tier": str(t.tier),
                        "stripe_product_id": t.stripe_product_id,
                        "stripe_monthly_price_id": t.stripe_monthly_price_id,
                        "stripe_yearly_price_id": t.stripe_yearly_price_id,
                    }
                )
    finally:
        await engine.dispose()

    snapshot = {
        "product": {
            "id": product.id,
            "name": product.name,
            "tax_code": product.tax_code,
        },
        "prices": [
            {
                "id": p.id,
                "interval": (p.get("recurring") or {}).get("interval"),
                "amount": p.unit_amount,
                "currency": p.currency,
                "tax_behavior": p.get("tax_behavior"),
                "active": p.active,
            }
            for p in prices
        ],
        "customers": {
            "total": customers_total,
            "with_country": customers_with_country,
            "by_country": countries,
        },
        "subscriptions": {
            "total": subs_total,
            "active": subs_active,
            "with_automatic_tax": subs_with_auto_tax,
            "by_price": subs_by_price,
        },
        "subscription_tiers": tier_rows,
    }

    summary_table = Table(show_header=False, padding=(0, 1))
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value")
    summary_table.add_row("Product tax_code", _safe(product.tax_code))
    summary_table.add_row("Prices", str(len(prices)))
    summary_table.add_row(
        "Customers (total / w/ country)",
        f"{customers_total} / {customers_with_country}",
    )
    summary_table.add_row(
        "Subscriptions (total / active / auto_tax)",
        f"{subs_total} / {subs_active} / {subs_with_auto_tax}",
    )
    summary_table.add_row("subscription_tier rows", str(len(tier_rows)))
    console.print(summary_table)

    _dump("migration-audit", snapshot)
    state.audit_before = snapshot
    return snapshot


# ---------------------------------------------------------------------------
# Phase 2 — Product tax_code
# ---------------------------------------------------------------------------


async def phase2_product_tax_code(cfg: RunConfig, state: MigrationState) -> None:
    _banner("Phase 2 — Set product tax_code")
    if not cfg.tax_code:
        logger.info(
            "No --tax-code provided; skipping. (Set STRIPE_CREDIT_TAX_CODE or pass --tax-code.)"
        )
        return

    client = _stripe(cfg.stripe_api_key)
    product = client.products.retrieve(cfg.product_id)

    if product.tax_code == cfg.tax_code:
        logger.info(f"Product already has tax_code={cfg.tax_code}. Nothing to do.")
        return

    logger.info(
        f"Plan: set product {product.id}.tax_code = {cfg.tax_code} (was: {product.tax_code or 'none'})"
    )
    decision = await _confirm_phase("Phase 2", cfg.dry_run)
    if decision != "yes":
        return

    if cfg.dry_run:
        logger.info("[DRY-RUN] Would call products.update(tax_code=...)")
    else:
        client.products.update(product.id, params={"tax_code": cfg.tax_code})
        logger.info(f"✅ tax_code set on {product.id}")
    state.product_tax_code_changed = True


# ---------------------------------------------------------------------------
# Phase 3 — Prices: clone to tax_behavior=exclusive
# ---------------------------------------------------------------------------


async def phase3_prices(cfg: RunConfig, state: MigrationState) -> None:
    _banner(
        "Phase 3 — Clone prices with tax_behavior=exclusive",
        (
            "Stripe locks `tax_behavior` once written, and even an "
            "`unspecified` price can't always be patched in place. "
            "This phase always creates a NEW price per active old price "
            "(same amount/currency/interval, tax_behavior=exclusive) and "
            "marks the old price inactive. Old → new ids feed Phase 5/6."
        ),
    )

    client = _stripe(cfg.stripe_api_key)
    prices = list(
        client.prices.list(
            params={"product": cfg.product_id, "limit": 100}
        ).auto_paging_iter()
    )

    plan_table = Table(
        title="Planned price actions", header_style="bold cyan", padding=(0, 1)
    )
    for col in ("Price ID", "Interval", "tax_behavior now", "Active", "Action"):
        plan_table.add_column(col)

    # action ∈ {"skip-inactive", "ok", "clone"}.
    # We deliberately do NOT include a "patch" branch — see the panel
    # text above. Clone-and-deactivate is the only path that works
    # uniformly across Stripe's tax_behavior states.
    actions: list[tuple[str, stripe.Price, str]] = []
    for p in prices:
        tb = p.get("tax_behavior") or "unspecified"
        if not p.active:
            # Deactivated price: leave it. If it's still referenced by
            # an active subscription, Phase 5 will surface that.
            actions.append(("skip-inactive", p, tb))
        elif tb == "exclusive":
            # Already migrated (idempotency: a previous run cloned it).
            actions.append(("ok", p, tb))
        else:
            actions.append(("clone", p, tb))

    for action, p, tb in actions:
        plan_table.add_row(
            p.id,
            (p.get("recurring") or {}).get("interval", "—"),
            tb,
            "yes" if p.active else "no",
            action,
        )
    console.print(plan_table)

    decision = await _confirm_phase("Phase 3", cfg.dry_run)
    if decision != "yes":
        return

    for action, p, _tb in actions:
        if action in ("ok", "skip-inactive"):
            state.price_actions.append({"price_id": p.id, "action": action})
            continue

        # action == "clone"
        params: dict[str, Any] = {
            "product": cfg.product_id,
            "currency": p.currency,
            "unit_amount": p.unit_amount,
            "tax_behavior": "exclusive",
            "nickname": (p.nickname or "") + " (tax-exclusive)",
            "metadata": dict(p.metadata or {}),
        }
        recurring = p.get("recurring")
        if recurring:
            params["recurring"] = {
                "interval": recurring.get("interval"),
                "interval_count": recurring.get("interval_count", 1),
            }

        if cfg.dry_run:
            new_id = f"price_DRYRUN_clone_of_{p.id}"
            logger.info(
                f"[DRY-RUN] prices.create(tax_behavior=exclusive, …) → {new_id}"
            )
            logger.info(f"[DRY-RUN] prices.update({p.id}, active=false)")
        else:
            new_price = client.prices.create(params=params)
            client.prices.update(p.id, params={"active": False})
            new_id = new_price.id
            logger.info(f"✅ cloned {p.id} → {new_id}; old marked inactive")

        state.price_clone_map[p.id] = new_id
        state.price_actions.append(
            {"price_id": p.id, "action": "cloned", "new_price_id": new_id}
        )

    if state.price_clone_map:
        console.print(
            Panel(
                "Prices were cloned. Active subscriptions on the old IDs will be migrated in Phase 5.",
                border_style="yellow",
                title="Heads up",
            )
        )


# ---------------------------------------------------------------------------
# Phase 4 — Customer billing addresses
# ---------------------------------------------------------------------------


async def phase4_customer_addresses(cfg: RunConfig, state: MigrationState) -> None:
    _banner(
        "Phase 4 — Customer billing addresses",
        "Audit + (optionally) backfill from Keycloak profiles.",
    )

    client = _stripe(cfg.stripe_api_key)
    engine = _db_engine(cfg.database_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Linked stripe_user rows are the source of truth for "platform users".
    try:
        async with Session() as session:
            su_rows = (await session.execute(select(StripeUser))).scalars().all()
    finally:
        await engine.dispose()

    plan_table = Table(
        title="Customer address audit", header_style="bold cyan", padding=(0, 1)
    )
    for col in ("Customer ID", "User ID", "Has country", "Action"):
        plan_table.add_column(col)

    no_address: list[dict[str, Any]] = []
    candidates: list[tuple[StripeUser, stripe.Customer]] = []

    for row in su_rows:
        if not row.stripe_customer_id:
            continue
        try:
            customer = client.customers.retrieve(row.stripe_customer_id)
        except stripe.InvalidRequestError:
            plan_table.add_row(
                row.stripe_customer_id, str(row.user_id), "—", "stripe-missing"
            )
            no_address.append(
                {
                    "user_id": str(row.user_id),
                    "stripe_customer_id": row.stripe_customer_id,
                    "missing_fields": "customer_not_in_stripe",
                }
            )
            continue

        country = (customer.address or {}).get("country") if customer.address else None
        if country:
            plan_table.add_row(customer.id, str(row.user_id), country, "ok")
            continue

        if cfg.address_policy == "attempt_keycloak_sync":
            plan_table.add_row(customer.id, str(row.user_id), "—", "kc-sync")
            candidates.append((row, customer))
        else:
            plan_table.add_row(customer.id, str(row.user_id), "—", "followup")
            no_address.append(
                {
                    "user_id": str(row.user_id),
                    "stripe_customer_id": customer.id,
                    "email": customer.email or "",
                    "missing_fields": "country",
                }
            )

    console.print(plan_table)

    decision = await _confirm_phase("Phase 4", cfg.dry_run)
    if decision != "yes":
        state.customers_no_address = no_address
        _dump_csv("migration-customers-no-address", no_address)
        return

    if cfg.address_policy == "attempt_keycloak_sync" and candidates:
        # Lazy import — Keycloak is heavy and the import has side effects.
        from virtual_labs.infrastructure.kc.config import KeycloakRealm

        for su, customer in candidates:
            try:
                kc_user = await KeycloakRealm.a_get_user(str(su.user_id))
            except Exception as e:
                logger.warning(f"   kc lookup failed for {su.user_id}: {e}")
                no_address.append(
                    {
                        "user_id": str(su.user_id),
                        "stripe_customer_id": customer.id,
                        "missing_fields": "keycloak_lookup_failed",
                    }
                )
                continue

            attrs = (kc_user or {}).get("attributes", {}) or {}

            def _first(key: str) -> Optional[str]:
                vals = attrs.get(key)
                if isinstance(vals, list) and vals:
                    return str(vals[0])
                if isinstance(vals, str):
                    return vals
                return None

            country = (_first("country") or "").upper() or None
            if not country:
                no_address.append(
                    {
                        "user_id": str(su.user_id),
                        "stripe_customer_id": customer.id,
                        "missing_fields": "kc_no_country",
                    }
                )
                continue

            address = {
                "country": country,
                "line1": _first("street") or None,
                "city": _first("locality") or None,
                "postal_code": _first("postal_code") or None,
                "state": _first("region") or None,
            }
            address = {k: v for k, v in address.items() if v}

            if cfg.dry_run:
                logger.info(
                    f"[DRY-RUN] customers.update({customer.id}, address={address})"
                )
            else:
                client.customers.update(customer.id, params={"address": address})
                logger.info(f"✅ updated {customer.id} address={address}")
            state.customer_actions.append(
                {
                    "customer_id": customer.id,
                    "user_id": str(su.user_id),
                    "address": address,
                }
            )

    state.customers_no_address = no_address
    _dump_csv("migration-customers-no-address", no_address)


# ---------------------------------------------------------------------------
# Phase 5 — Active subscriptions
# ---------------------------------------------------------------------------


async def phase5_active_subscriptions(cfg: RunConfig, state: MigrationState) -> None:
    _banner(
        "Phase 5 — Active subscriptions",
        "Swap cloned prices and turn on automatic_tax where eligible.",
    )

    client = _stripe(cfg.stripe_api_key)
    subs = list(
        client.subscriptions.list(
            params={
                "status": "active",
                "limit": 100,
                "expand": ["data.items.data.price", "data.customer"],
            }
        ).auto_paging_iter()
    )

    plan_table = Table(
        title="Planned subscription updates", header_style="bold cyan", padding=(0, 1)
    )
    for col in (
        "Sub ID",
        "Customer",
        "Country",
        "Current price",
        "Target price",
        "auto_tax",
    ):
        plan_table.add_column(col)

    plans: list[dict[str, Any]] = []
    for sub in subs:
        item = (sub.get("items") or {}).get("data", [None])[0]
        cur_price = (item or {}).get("price", {}).get("id") if item else None
        target_price = state.price_clone_map.get(cur_price or "", cur_price)

        cust = sub.customer
        cust_id = cust if isinstance(cust, str) else cust.id
        cust_country = None
        if not isinstance(cust, str):
            cust_country = (cust.address or {}).get("country") if cust.address else None

        already_on = (sub.get("automatic_tax") or {}).get("enabled")
        eligible = bool(cust_country and cust_country.upper() in cfg.tax_countries)
        plan_table.add_row(
            sub.id,
            cust_id,
            cust_country or "—",
            cur_price or "—",
            target_price or "—",
            "yes" if already_on else ("→on" if eligible else "skip"),
        )
        plans.append(
            {
                "sub_id": sub.id,
                "item_id": (item or {}).get("id"),
                "current_price": cur_price,
                "target_price": target_price,
                "country": cust_country,
                "auto_tax_already_on": bool(already_on),
                "make_auto_tax_on": eligible and not already_on,
                "swap_price": target_price != cur_price and target_price is not None,
            }
        )

    console.print(plan_table)

    decision = await _confirm_phase("Phase 5", cfg.dry_run)
    if decision != "yes":
        return

    for plan in plans:
        params: dict[str, Any] = {}
        if plan["swap_price"] and plan["item_id"]:
            # Always at_period_end: no proration, no mid-cycle invoice.
            # The swap takes effect at the next renewal; the existing
            # `customer.subscription.updated` webhook then reconciles
            # `paid_subscription.stripe_price_id` (so Phase 6 below
            # only touches `subscription_tier`).
            #
            # NOTE: for true phase-anchored swaps Stripe recommends
            # `subscription_schedules.create_from_subscription`. The
            # simpler `subscriptions.update(items=..., proration_behavior=none)`
            # used here is good enough when the subscription has no
            # scheduled phase changes; if your billing team has any,
            # switch to subscription_schedules.
            params["items"] = [{"id": plan["item_id"], "price": plan["target_price"]}]
            params["proration_behavior"] = "none"
        if plan["make_auto_tax_on"]:
            params["automatic_tax"] = {"enabled": True}

        if not params:
            continue

        if cfg.dry_run:
            logger.info(f"[DRY-RUN] subscriptions.update({plan['sub_id']}, {params})")
        else:
            client.subscriptions.update(plan["sub_id"], params=params)
            logger.info(f"✅ updated {plan['sub_id']}")
        state.subscription_actions.append({"sub_id": plan["sub_id"], "params": params})


# ---------------------------------------------------------------------------
# Phase 6 — DB reconciliation
# ---------------------------------------------------------------------------


async def phase6_db_reconciliation(cfg: RunConfig, state: MigrationState) -> None:
    _banner(
        "Phase 6 — DB reconciliation",
        (
            "Update `subscription_tier` rows so new sign-ups use the new "
            "tax-exclusive price IDs. We deliberately do NOT touch "
            "`paid_subscription.stripe_price_id` here: every active sub "
            "swaps at the end of its current period, and the existing "
            "`customer.subscription.updated` webhook reconciles the local "
            "row when the swap actually fires. Touching it now would put "
            "the DB ahead of Stripe's truth."
        ),
    )

    if not state.price_clone_map:
        logger.info("No price clones recorded; nothing to reconcile.")
        return

    decision = await _confirm_phase("Phase 6", cfg.dry_run)
    if decision != "yes":
        return

    engine = _db_engine(cfg.database_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            for old_id, new_id in state.price_clone_map.items():
                if cfg.dry_run:
                    logger.info(
                        f"[DRY-RUN] subscription_tier: monthly|yearly_price={old_id} → {new_id}"
                    )
                    logger.info(
                        "[DRY-RUN] paid_subscription rows: NOT touched "
                        "(handled by customer.subscription.updated webhook)"
                    )
                    continue

                await session.execute(
                    update(SubscriptionTier)
                    .where(SubscriptionTier.stripe_monthly_price_id == old_id)
                    .values(stripe_monthly_price_id=new_id)
                )
                await session.execute(
                    update(SubscriptionTier)
                    .where(SubscriptionTier.stripe_yearly_price_id == old_id)
                    .values(stripe_yearly_price_id=new_id)
                )
                state.db_actions.append({"old_price": old_id, "new_price": new_id})

            if not cfg.dry_run:
                await session.commit()
                logger.info("✅ DB reconciliation committed")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Phase 7 — Final summary
# ---------------------------------------------------------------------------


async def phase7_summary(cfg: RunConfig, state: MigrationState) -> None:
    _banner("Phase 7 — Final summary")
    state.audit_after = await phase1_audit(cfg, state)  # re-runs audit for the diff

    payload = {
        "config": {
            "apply": cfg.apply,
            "product_id": cfg.product_id,
            "tax_code": cfg.tax_code,
            "tax_countries": cfg.tax_countries,
            "swap_policy": "at_period_end",
            "address_policy": cfg.address_policy,
        },
        "audit_before": state.audit_before,
        "audit_after": state.audit_after,
        "product_tax_code_changed": state.product_tax_code_changed,
        "price_actions": state.price_actions,
        "price_clone_map": state.price_clone_map,
        "customer_actions": state.customer_actions,
        "customers_no_address": state.customers_no_address,
        "subscription_actions": state.subscription_actions,
        "db_actions": state.db_actions,
    }
    _dump("migration-summary", payload)

    summary = Table(show_header=False, padding=(0, 1))
    summary.add_column("Bucket", style="bold")
    summary.add_column("Count")
    summary.add_row("price actions", str(len(state.price_actions)))
    summary.add_row("price clones", str(len(state.price_clone_map)))
    summary.add_row("customer address writes", str(len(state.customer_actions)))
    summary.add_row("customers needing followup", str(len(state.customers_no_address)))
    summary.add_row("subscription updates", str(len(state.subscription_actions)))
    summary.add_row("DB updates", str(len(state.db_actions)))
    console.print(summary)
    console.print(
        f"[dim]All artefacts written under {OUT_DIR}/. Keep these as the change log.[/]"
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


PHASES: list[tuple[str, Any]] = [
    ("phase0_preflight", phase0_preflight),
    ("phase1_audit", phase1_audit),
    ("phase2_product_tax_code", phase2_product_tax_code),
    ("phase3_prices", phase3_prices),
    ("phase4_customer_addresses", phase4_customer_addresses),
    ("phase5_active_subscriptions", phase5_active_subscriptions),
    ("phase6_db_reconciliation", phase6_db_reconciliation),
    ("phase7_summary", phase7_summary),
]


def _parse_args() -> RunConfig:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(description="Migrate to tax-aware billing.")
    parser.add_argument("--product-id", default=os.getenv("PROD_ID"))
    parser.add_argument("--tax-code", default=os.getenv("STRIPE_CREDIT_TAX_CODE"))
    parser.add_argument(
        "--tax-countries",
        default=os.getenv("BILLING_TAX_ENABLED_COUNTRIES", "CH"),
        help="Comma-separated ISO-3166-1 alpha-2.",
    )
    parser.add_argument(
        "--address-policy",
        choices=("mark_for_followup", "attempt_keycloak_sync"),
        default="mark_for_followup",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Without this flag the script is read-only.",
    )
    args = parser.parse_args()

    api_key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY") or ""
    db_url = (
        os.getenv("DATABASE_URL") or "postgresql+asyncpg://vlm:vlm@localhost:15432/vlm"
    )

    if not api_key:
        logger.error("STRIPE_SECRET_KEY (or STRIPE_API_KEY) is required.")
        raise SystemExit(2)
    if not args.product_id:
        logger.error("--product-id (or PROD_ID env) is required.")
        raise SystemExit(2)

    return RunConfig(
        stripe_api_key=api_key,
        database_url=db_url,
        product_id=args.product_id,
        tax_code=args.tax_code or None,
        tax_countries=[
            c.strip().upper() for c in args.tax_countries.split(",") if c.strip()
        ],
        address_policy=cast(AddressPolicy, args.address_policy),
        apply=bool(args.apply),
    )


async def _amain(cfg: RunConfig) -> int:
    state = MigrationState()
    try:
        for name, fn in PHASES:
            await fn(cfg, state) if name != "phase0_preflight" else await fn(cfg)
            if name == "phase0_preflight":
                _banner(
                    "Ready",
                    "Phase 0 done. The runner can audit the settings above and abort here. "
                    "Press Ctrl-C to stop, or continue to Phase 1.",
                    style="green",
                )
                if not await inquirer.confirm(
                    message="Continue?", default=True
                ).execute_async():
                    return 0
        return 0
    except KeyboardInterrupt:
        logger.warning("Aborted by operator.")
        return 130


def run() -> int:
    cfg = _parse_args()
    return asyncio.run(_amain(cfg))


if __name__ == "__main__":
    sys.exit(run())
