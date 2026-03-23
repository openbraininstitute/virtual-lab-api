#!/usr/bin/env python3
"""
Interactive CLI to manage Stripe subscription coupons.

Menu-driven flow:
  • List customers
  • List subscriptions (with status filter)
  • List active coupons
  • Apply coupon to subscriptions (all or specific)
  • Inspect a subscription (details + invoices)

Usage:
    python scripts/manage_stripe_coupons.py
    poetry run manage-coupons

Requires:
    poetry add rich InquirerPy
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

import stripe
from InquirerPy import inquirer
from InquirerPy.separator import Separator
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
logger.configure(handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}])



def _ts(ts: Optional[int]) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _currency_fmt(amount: Optional[int], currency: str = "usd") -> str:
    if amount is None:
        return "—"
    return f"{amount / 100:,.2f} {currency.upper()}"


def _safe(val: Optional[str], max_len: int = 0) -> str:
    if not val:
        return "—"
    if max_len and len(val) > max_len:
        return val[: max_len - 1] + "…"
    return val


def _status_style(status: str) -> str:
    return {
        "active": "green", "trialing": "cyan", "canceled": "red",
        "past_due": "yellow", "unpaid": "red", "paused": "dim",
    }.get(status, "white")


def _extract_customer_info(sub: stripe.Subscription) -> tuple[str, str, str]:
    customer = sub.customer
    cust_id = customer if isinstance(customer, str) else customer.id
    name, email = "—", "—"
    if not isinstance(customer, str):
        name = getattr(customer, "name", None) or "—"
        email = getattr(customer, "email", None) or "—"
    return name, email, cust_id


def _extract_plan_info(sub: stripe.Subscription) -> tuple[str, str]:
    sub_items = sub.get("items")
    if not sub_items or not sub_items.get("data"):
        return "—", "—"
    price = sub_items["data"][0].get("price")
    if not price:
        return "—", "—"
    product = price.get("product", "—")
    plan_name = product if isinstance(product, str) else getattr(product, "name", "—")
    recurring = price.get("recurring")
    interval = recurring.get("interval", "—") if recurring else "—"
    return _safe(plan_name, 24), interval

def _extract_plan_info(sub: stripe.Subscription) -> tuple[str, str]:
    """Return (plan_name, interval) from a subscription."""
    sub_items = sub.get("items")
    if not sub_items or not sub_items.get("data"):
        return "—", "—"
    price = sub_items["data"][0].get("price")
    if not price:
        return "—", "—"
    product = price.get("product", "—")
    plan_name = product if isinstance(product, str) else getattr(product, "name", "—")
    recurring = price.get("recurring")
    interval = recurring.get("interval", "—") if recurring else "—"
    return _safe(plan_name, 24), interval


def _get_interval(sub: stripe.Subscription) -> str:
    """Return the raw billing interval string ('month', 'year', etc.) or 'unknown'."""
    sub_items = sub.get("items")
    if not sub_items or not sub_items.get("data"):
        return "unknown"
    price = sub_items["data"][0].get("price")
    if not price:
        return "unknown"
    recurring = price.get("recurring")
    if not recurring:
        return "unknown"
    return recurring.get("interval", "unknown")


def _collect_plan_intervals(subs: list[stripe.Subscription]) -> list[str]:
    """Return sorted unique billing intervals across subscriptions."""
    intervals = set()
    for sub in subs:
        intervals.add(_get_interval(sub))
    return sorted(intervals)



class StripeCouponManager:
    def __init__(self, api_key: str) -> None:
        self.client = stripe.StripeClient(api_key=api_key)

    def fetch_subscriptions(self, status_filter: str = "all") -> list[stripe.Subscription]:
        logger.info(f"Fetching subscriptions (filter={status_filter}) …")
        if status_filter == "active":
            statuses = ["active", "trialing"]
        elif status_filter == "inactive":
            statuses = ["canceled", "past_due", "unpaid", "incomplete", "incomplete_expired", "paused"]
        else:
            statuses = ["active", "trialing", "canceled", "past_due", "unpaid", "incomplete", "incomplete_expired", "paused"]

        result: list[stripe.Subscription] = []
        for status in statuses:
            for sub in self.client.subscriptions.list(
                params={"status": status, "limit": 100, "expand": ["data.customer"]}
            ).auto_paging_iter():
                result.append(sub)
        logger.info(f"Fetched {len(result)} subscriptions")
        return result

    def fetch_customers(self) -> list[stripe.Customer]:
        logger.info("Fetching customers …")
        customers = list(self.client.customers.list(params={"limit": 100}).auto_paging_iter())
        logger.info(f"Fetched {len(customers)} customers")
        return customers

    def fetch_active_coupons(self) -> list[stripe.Coupon]:
        logger.info("Fetching active coupons …")
        coupons = [c for c in self.client.coupons.list(params={"limit": 100}).auto_paging_iter() if c.valid]
        logger.info(f"Found {len(coupons)} active coupons")
        return coupons

    def fetch_invoices(self, subscription_id: str) -> list[stripe.Invoice]:
        return list(self.client.invoices.list(
            params={"subscription": subscription_id, "limit": 50}
        ).auto_paging_iter())

    def apply_coupon(self, subscription_id: str, coupon_id: str) -> stripe.Subscription:
        return self.client.subscriptions.update(subscription_id, params={"discounts": [
            {"coupon": coupon_id}
        ]})



def show_customers(customers: list[stripe.Customer]) -> None:
    table = Table(title=f"Customers ({len(customers)})", header_style="bold cyan", row_styles=["", "dim"], padding=(0, 1))
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("Name", min_width=20, max_width=30)
    table.add_column("Email", min_width=22, max_width=35)
    table.add_column("Customer ID", no_wrap=True, style="dim")
    for i, c in enumerate(customers, 1):
        table.add_row(str(i), _safe(c.name, 28), _safe(c.email, 33), c.id)
    console.print(table)


def show_subscriptions(subs: list[stripe.Subscription]) -> None:
    table = Table(title=f"Subscriptions ({len(subs)})", header_style="bold cyan", row_styles=["", "dim"], padding=(0, 1))
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("Customer", min_width=16, max_width=24)
    table.add_column("Email", min_width=18, max_width=30)
    table.add_column("Customer ID", no_wrap=True, style="dim")
    table.add_column("Subscription ID", no_wrap=True)
    table.add_column("Status", width=10)
    table.add_column("Plan", min_width=10, max_width=24)
    table.add_column("Interval", width=9)
    table.add_column("Start", width=11)
    table.add_column("Period End", width=11)
    table.add_column("Coupon", min_width=10, max_width=22)

    for i, sub in enumerate(subs, 1):
        name, email, cust_id = _extract_customer_info(sub)
        plan_name, interval = _extract_plan_info(sub)
        coupon = "—"
        if sub.discount and sub.discount.coupon:
            coupon = sub.discount.coupon.name or sub.discount.coupon.id
        table.add_row(
            str(i), _safe(name, 22), _safe(email, 28), cust_id, sub.id,
            Text(sub.status or "—", style=_status_style(sub.status or "")),
            plan_name, interval, _ts(sub.start_date), _ts(sub.current_period_end), _safe(coupon, 20),
        )
    console.print(table)


def show_coupons(coupons: list[stripe.Coupon]) -> None:
    table = Table(title=f"Active Coupons ({len(coupons)})", header_style="bold cyan", row_styles=["", "dim"], padding=(0, 1))
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("Coupon ID", no_wrap=True)
    table.add_column("Name", min_width=14, max_width=28)
    table.add_column("Discount", width=18)
    table.add_column("Duration", width=14)
    table.add_column("Redeem By", width=11)
    for i, c in enumerate(coupons, 1):
        if c.percent_off:
            disc = f"{c.percent_off}% off"
        elif c.amount_off:
            disc = f"{_currency_fmt(c.amount_off, c.currency or 'usd')} off"
        else:
            disc = "—"
        table.add_row(str(i), c.id, _safe(c.name, 26), disc, c.duration or "—", _ts(c.redeem_by))
    console.print(table)


def show_subscription_detail(mgr: StripeCouponManager, sub: stripe.Subscription) -> None:
    name, email, cust_id = _extract_customer_info(sub)
    plan_name, interval = _extract_plan_info(sub)
    coupon_label = "none"
    if sub.discount and sub.discount.coupon:
        coupon_label = sub.discount.coupon.name or sub.discount.coupon.id

    lines = [
        f"[bold]Subscription:[/]  {sub.id}",
        f"[bold]Customer:[/]      {name} ({email})",
        f"[bold]Customer ID:[/]   {cust_id}",
        f"[bold]Status:[/]        [{_status_style(sub.status or '')}]{sub.status}[/]",
        f"[bold]Plan:[/]          {plan_name}  /  {interval}",
        f"[bold]Created:[/]       {_ts(sub.created)}",
        f"[bold]Period:[/]        {_ts(sub.current_period_start)} → {_ts(sub.current_period_end)}",
        f"[bold]Coupon:[/]        {coupon_label}",
    ]
    sub_items = sub.get("items")
    if sub_items and sub_items.get("data"):
        lines += ["", "[bold underline]Line Items[/]"]
        for item in sub_items["data"]:
            p = item.get("price", {})
            prod = p.get("product", "—")
            if not isinstance(prod, str):
                prod = getattr(prod, "name", "—")
            rec = p.get("recurring")
            iv = rec.get("interval", "—") if rec else "—"
            lines.append(f"  • {prod} — {_currency_fmt(p.get('unit_amount'), p.get('currency', 'usd'))} / {iv}")

    console.print(Panel("\n".join(lines), title=f"[bold]{sub.id}[/]", border_style="cyan", padding=(1, 2)))

    invoices = mgr.fetch_invoices(sub.id)
    if invoices:
        inv_table = Table(title=f"Invoices ({len(invoices)})", header_style="bold magenta", row_styles=["", "dim"], padding=(0, 1))
        inv_table.add_column("Invoice ID", no_wrap=True, style="dim")
        inv_table.add_column("Date", width=11)
        inv_table.add_column("Amount", width=16, justify="right")
        inv_table.add_column("Status", width=12)
        inv_table.add_column("Paid", width=5)
        for inv in invoices:
            inv_table.add_row(
                inv.id, _ts(inv.created), _currency_fmt(inv.amount_due, inv.currency),
                inv.status or "—", Text("yes", style="green") if inv.paid else Text("no", style="red"),
            )
        console.print(inv_table)
    else:
        console.print("[dim]  No invoices found.[/]")




def action_list_customers(mgr: StripeCouponManager) -> None:
    customers = mgr.fetch_customers()
    if not customers:
        console.print("[yellow]No customers found.[/]")
        return
    show_customers(customers)


def action_list_subscriptions(mgr: StripeCouponManager) -> list[stripe.Subscription]:
    status = inquirer.select(
        message="Filter by status:",
        choices=["active", "inactive", "all"],
        default="active",
    ).execute()
    subs = mgr.fetch_subscriptions(status_filter=status)
    if not subs:
        console.print("[yellow]No subscriptions match the filter.[/]")
        return []

    # Optional plan/interval filter
    intervals = _collect_plan_intervals(subs)
    if len(intervals) > 1:
        interval_choices = [{"name": "all", "value": "all"}] + [
            {"name": iv, "value": iv} for iv in intervals
        ]
        plan_filter = inquirer.select(
            message="Filter by plan interval:",
            choices=interval_choices,
            default="all",
        ).execute()
        if plan_filter != "all":
            subs = [s for s in subs if _get_interval(s) == plan_filter]

    if not subs:
        console.print("[yellow]No subscriptions match the filters.[/]")
        return []

    show_subscriptions(subs)

    # Offer to inspect one
    inspect = inquirer.confirm(message="Inspect a specific subscription?", default=False).execute()
    if inspect:
        choices = [{"name": f"{s.id}  ({_extract_customer_info(s)[0]})", "value": s} for s in subs]
        selected = inquirer.fuzzy(
            message="Search / select subscription:",
            choices=choices,
        ).execute()
        show_subscription_detail(mgr, selected)

    return subs


def action_list_coupons(mgr: StripeCouponManager) -> list[stripe.Coupon]:
    coupons = mgr.fetch_active_coupons()
    if not coupons:
        console.print("[yellow]No active coupons found.[/]")
        return []
    show_coupons(coupons)
    return coupons


def action_apply_coupon(mgr: StripeCouponManager) -> None:
    # 1. Choose scope: all / per plan / specific
    scope = inquirer.select(
        message="Apply coupon to:",
        choices=[
            {"name": "All active subscriptions", "value": "all"},
            {"name": "By plan interval (monthly / yearly)", "value": "plan"},
            {"name": "Specific subscriptions", "value": "specific"},
        ],
    ).execute()

    # 2. Fetch active subscriptions
    subs = mgr.fetch_subscriptions(status_filter="active")
    if not subs:
        console.print("[yellow]No active subscriptions found.[/]")
        return

    # 3. Narrow down based on scope
    if scope == "plan":
        intervals = _collect_plan_intervals(subs)
        if not intervals:
            console.print("[yellow]Could not determine plan intervals.[/]")
            return
        chosen_interval = inquirer.select(
            message="Select plan interval:",
            choices=intervals,
        ).execute()
        selected = [s for s in subs if _get_interval(s) == chosen_interval]
        if not selected:
            console.print(f"[yellow]No subscriptions with interval '{chosen_interval}'.[/]")
            return

    elif scope == "specific":
        sub_choices = [
            {
                "name": f"{s.id}  ({_extract_customer_info(s)[0]}  /  {_extract_customer_info(s)[1]}  /  {_get_interval(s)})",
                "value": s,
            }
            for s in subs
        ]
        selected = inquirer.checkbox(
            message="Select subscriptions (space to toggle, enter to confirm):",
            choices=sub_choices,
        ).execute()
        if not selected:
            console.print("[yellow]No subscriptions selected.[/]")
            return
    else:
        selected = subs

    # 4. Show the subscriptions that will be updated
    console.print(f"\n[bold]{len(selected)}[/] subscription(s) will be updated:\n")
    show_subscriptions(selected)

    # 5. Pick coupon
    coupons = mgr.fetch_active_coupons()
    if not coupons:
        console.print("[yellow]No active coupons available.[/]")
        return

    coupon_choices = []
    for c in coupons:
        if c.percent_off:
            label = f"{c.id}  —  {c.name or '(no name)'}  ({c.percent_off}% off)"
        elif c.amount_off:
            label = f"{c.id}  —  {c.name or '(no name)'}  ({_currency_fmt(c.amount_off, c.currency or 'usd')} off)"
        else:
            label = f"{c.id}  —  {c.name or '(no name)'}"
        coupon_choices.append({"name": label, "value": c.id})
    coupon_id = inquirer.fuzzy(
        message="Select coupon to apply:",
        choices=coupon_choices,
    ).execute()

    # 6. Confirm
    console.print(f"\nApplying coupon [bold]{coupon_id}[/] to [bold]{len(selected)}[/] subscription(s).")
    confirm = inquirer.confirm(message="Proceed?", default=False).execute()
    if not confirm:
        console.print("[dim]Cancelled.[/]")
        return

    # 7. Apply and show results
    results = Table(title="Update Results", header_style="bold", padding=(0, 1))
    results.add_column("Subscription ID", no_wrap=True)
    results.add_column("Customer", min_width=16, max_width=26)
    results.add_column("Interval", width=9)
    results.add_column("Result", width=10)
    results.add_column("Detail", max_width=60)

    success, failed = 0, 0
    for sub in selected:
        name, _, _ = _extract_customer_info(sub)
        interval = _get_interval(sub)
        try:
            mgr.apply_coupon(sub.id, coupon_id)
            results.add_row(sub.id, _safe(name, 24), interval, Text("✅ OK", style="green"), "coupon applied")
            success += 1
        except Exception as e:
            results.add_row(sub.id, _safe(name, 24), interval, Text("❌ FAIL", style="red"), str(e)[:80])
            failed += 1

    console.print(results)
    console.print(f"\n[bold]{success}[/] succeeded, [bold]{failed}[/] failed out of {len(selected)} total.")



MENU_CHOICES = [
    {"name": "📋  List customers", "value": "customers"},
    {"name": "📦  List subscriptions", "value": "subscriptions"},
    {"name": "🏷️   List active coupons", "value": "coupons"},
    Separator(),
    {"name": "✏️   Apply coupon to subscriptions", "value": "apply"},
    Separator(),
    {"name": "🚪  Exit", "value": "exit"},
]


def main() -> int:
    console.print(Panel("[bold]Stripe Subscription Coupon Manager[/]", border_style="bright_blue", padding=(1, 4)))

    # Step 1: API key
    api_key = inquirer.secret(
        message="Enter your Stripe secret key (sk_…):",
        validate=lambda val: val.startswith("sk_") or "Key must start with 'sk_'",
    ).execute()

    try:
        client = stripe.StripeClient(api_key=api_key)
        client.customers.list(params={"limit": 1})
        logger.info("✅ Stripe key validated")
    except stripe.AuthenticationError:
        logger.error("❌ Authentication failed. Check your key.")
        return 1
    except Exception as e:
        logger.error(f"❌ Error validating key: {e}")
        return 1

    mgr = StripeCouponManager(api_key)

    # Menu loop
    while True:
        try:
            action = inquirer.select(
                message="What would you like to do?",
                choices=MENU_CHOICES,
                pointer="❯",
            ).execute()

            if action == "exit":
                console.print("[dim]Bye 👋[/]")
                break
            elif action == "customers":
                action_list_customers(mgr)
            elif action == "subscriptions":
                action_list_subscriptions(mgr)
            elif action == "coupons":
                action_list_coupons(mgr)
            elif action == "apply":
                action_apply_coupon(mgr)

        except KeyboardInterrupt:
            console.print("\n[dim]Aborted.[/]")
            break

    return 0


def run_async() -> int:
    """Entry point for poetry script command."""
    return main()


if __name__ == "__main__":
    sys.exit(main())
