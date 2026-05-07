#!/usr/bin/env python3
"""
CLI script to update virtual lab reference_email based on owner user emails.

Reads a CSV file containing user IDs and emails, finds virtual labs owned by
each user, and updates the virtual lab's reference_email to match the user's
email from the CSV.

Features:
  • Dry-run mode (default) — shows what would change without modifying the DB
  • Live mode — actually applies the updates after explicit confirmation
  • Database connection health check with version info
  • Detailed reporting with color-coded status for each virtual lab
  • Handles edge cases: missing virtual labs, already-matching emails, users
    with multiple labs

Usage:
    python scripts/update_vlab_reference_email.py
    poetry run update-vlab-email

Requires:
    poetry add rich InquirerPy
"""

from __future__ import annotations

import csv
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, NamedTuple

from InquirerPy import inquirer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class UpdateStatus(Enum):
    WILL_CHANGE_MISSING = "will_change_missing"
    WILL_CHANGE_MISMATCH = "will_change_mismatch"
    ALREADY_MATCHES = "already_matches"
    NO_VLAB = "no_vlab"
    NO_EMAIL_SET = "no_email_set"
    MISMATCH_SKIPPED = "mismatch_skipped"
    MISSING_SKIPPED = "missing_skipped"
    UPDATED = "updated"
    FAILED = "failed"
    SKIPPED = "skipped"


class UpdateScope(Enum):
    MISSING_ONLY = "missing_only"
    MISMATCH_ONLY = "mismatch_only"
    BOTH = "both"


class VLabResult(NamedTuple):
    user_id: str
    user_email: str
    vlab_id: str
    vlab_name: str
    current_email: str
    new_email: str
    status: UpdateStatus
    detail: str


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def load_csv(file_path: Path) -> List[Dict[str, str]]:
    """
    Load and validate a CSV file with 'id' and 'email' columns.

    Returns a list of dicts with keys 'id' and 'email'.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    rows: List[Dict[str, str]] = []
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header row")

        # Normalize header names (strip whitespace, lowercase for matching)
        normalized_fields = {h.strip().lower(): h for h in reader.fieldnames}

        if "id" not in normalized_fields:
            raise ValueError(
                f"CSV must have an 'id' column. Found columns: {list(reader.fieldnames)}"
            )
        if "email" not in normalized_fields:
            raise ValueError(
                f"CSV must have an 'email' column. Found columns: {list(reader.fieldnames)}"
            )

        id_col = normalized_fields["id"]
        email_col = normalized_fields["email"]

        for i, row in enumerate(reader, start=2):  # start=2 because row 1 is header
            user_id = (row.get(id_col) or "").strip()
            email = (row.get(email_col) or "").strip()

            if not user_id:
                logger.warning(f"Row {i}: skipping — empty user ID")
                continue
            if not email:
                logger.warning(f"Row {i}: skipping — empty email for user {user_id}")
                continue

            rows.append({"id": user_id, "email": email})

    return rows


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------


class DatabaseConnection:
    """Manages a synchronous SQLAlchemy connection to the virtual labs DB."""

    def __init__(self, connection_string: str) -> None:
        from sqlalchemy import create_engine, text

        self.engine = create_engine(connection_string, echo=False)
        self._text = text

        # Test connection
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        logger.info(f"Connected to database")

    def get_db_info(self) -> Dict[str, Any]:
        """Get database version and connection info."""
        from sqlalchemy import text

        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar() or "unknown"

            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar() or "unknown"

            result = conn.execute(
                text("SELECT count(*) FROM virtual_lab WHERE deleted = false")
            )
            vlab_count = result.scalar() or 0

        return {
            "version": version,
            "database": db_name,
            "active_vlabs": vlab_count,
        }

    def find_vlabs_by_owners(self, owner_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Find all non-deleted virtual labs for a list of owner IDs in a single query.

        Returns a dict mapping owner_id -> list of virtual labs.
        """
        from sqlalchemy import text

        if not owner_ids:
            return {}

        query = text("""
            SELECT id, name, reference_email, owner_id::text, created_at
            FROM virtual_lab
            WHERE owner_id = ANY(CAST(:owner_ids AS uuid[])) AND deleted = false
            ORDER BY created_at
        """)

        result_map: Dict[str, List[Dict[str, Any]]] = {uid: [] for uid in owner_ids}

        with self.engine.connect() as conn:
            result = conn.execute(query, {"owner_ids": owner_ids})
            for row in result.mappings():
                row_dict = dict(row)
                oid = str(row_dict["owner_id"])
                if oid in result_map:
                    result_map[oid].append(row_dict)

        return result_map

    def update_reference_email(self, vlab_id: str, new_email: str) -> None:
        """Update the reference_email for a virtual lab."""
        from sqlalchemy import text

        query = text("""
            UPDATE virtual_lab
            SET reference_email = :email, updated_at = NOW()
            WHERE id = :vlab_id
        """)

        with self.engine.connect() as conn:
            conn.execute(query, {"email": new_email, "vlab_id": vlab_id})
            conn.commit()


# ---------------------------------------------------------------------------
# Analysis & update logic
# ---------------------------------------------------------------------------


def analyze_users(
    db: DatabaseConnection,
    users: List[Dict[str, str]],
    scope: UpdateScope,
) -> List[VLabResult]:
    """
    For each user in the CSV, find their virtual labs and determine what
    action is needed. Uses a single DB query for all users.
    """
    results: List[VLabResult] = []
    user_ids = [u["id"] for u in users]

    try:
        vlabs_by_owner = db.find_vlabs_by_owners(user_ids)
    except Exception as e:
        console.print(f"[red]Failed to query virtual labs:[/] {e}")
        for user in users:
            results.append(VLabResult(
                user_id=user["id"],
                user_email=user["email"],
                vlab_id="—",
                vlab_name="—",
                current_email="—",
                new_email=user["email"],
                status=UpdateStatus.FAILED,
                detail=f"DB query failed: {e}",
            ))
        return results

    for user in users:
        user_id = user["id"]
        user_email = user["email"]
        vlabs = vlabs_by_owner.get(user_id, [])

        if not vlabs:
            results.append(VLabResult(
                user_id=user_id,
                user_email=user_email,
                vlab_id="—",
                vlab_name="—",
                current_email="—",
                new_email=user_email,
                status=UpdateStatus.NO_VLAB,
                detail="No virtual lab found for this owner",
            ))
            continue

        for vlab in vlabs:
            vlab_id = str(vlab["id"])
            vlab_name = vlab["name"] or "—"
            current_email = vlab["reference_email"] or ""

            if not current_email:
                # Missing email case
                if scope in (UpdateScope.MISSING_ONLY, UpdateScope.BOTH):
                    results.append(VLabResult(
                        user_id=user_id,
                        user_email=user_email,
                        vlab_id=vlab_id,
                        vlab_name=vlab_name,
                        current_email="(empty)",
                        new_email=user_email,
                        status=UpdateStatus.WILL_CHANGE_MISSING,
                        detail=f'"(empty)" → "{user_email}"',
                    ))
                else:
                    results.append(VLabResult(
                        user_id=user_id,
                        user_email=user_email,
                        vlab_id=vlab_id,
                        vlab_name=vlab_name,
                        current_email="(empty)",
                        new_email=user_email,
                        status=UpdateStatus.MISSING_SKIPPED,
                        detail="Skipped — scope excludes missing emails",
                    ))
            elif current_email.lower() == user_email.lower():
                results.append(VLabResult(
                    user_id=user_id,
                    user_email=user_email,
                    vlab_id=vlab_id,
                    vlab_name=vlab_name,
                    current_email=current_email,
                    new_email=user_email,
                    status=UpdateStatus.ALREADY_MATCHES,
                    detail="Email already matches — no change needed",
                ))
            else:
                # Mismatch case
                if scope in (UpdateScope.MISMATCH_ONLY, UpdateScope.BOTH):
                    results.append(VLabResult(
                        user_id=user_id,
                        user_email=user_email,
                        vlab_id=vlab_id,
                        vlab_name=vlab_name,
                        current_email=current_email,
                        new_email=user_email,
                        status=UpdateStatus.WILL_CHANGE_MISMATCH,
                        detail=f'"{current_email}" → "{user_email}"',
                    ))
                else:
                    results.append(VLabResult(
                        user_id=user_id,
                        user_email=user_email,
                        vlab_id=vlab_id,
                        vlab_name=vlab_name,
                        current_email=current_email,
                        new_email=user_email,
                        status=UpdateStatus.MISMATCH_SKIPPED,
                        detail=f'Skipped — scope excludes mismatches ("{current_email}")',
                    ))

    return results


def apply_updates(
    db: DatabaseConnection,
    results: List[VLabResult],
) -> List[VLabResult]:
    """
    Apply the actual updates to the database for results with WILL_UPDATE status.

    Returns a new list with updated statuses.
    """
    final_results: List[VLabResult] = []

    for result in results:
        if result.status not in (UpdateStatus.WILL_CHANGE_MISSING, UpdateStatus.WILL_CHANGE_MISMATCH):
            final_results.append(result)
            continue

        try:
            db.update_reference_email(result.vlab_id, result.new_email)
            final_results.append(result._replace(
                status=UpdateStatus.UPDATED,
                detail=f'Updated: "{result.current_email}" → "{result.new_email}"',
            ))
        except Exception as e:
            final_results.append(result._replace(
                status=UpdateStatus.FAILED,
                detail=f"Update failed: {e}",
            ))

    return final_results


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _status_style(status: UpdateStatus) -> str:
    return {
        UpdateStatus.WILL_CHANGE_MISSING: "yellow",
        UpdateStatus.WILL_CHANGE_MISMATCH: "magenta",
        UpdateStatus.ALREADY_MATCHES: "green",
        UpdateStatus.NO_VLAB: "dim",
        UpdateStatus.NO_EMAIL_SET: "dim",
        UpdateStatus.MISMATCH_SKIPPED: "cyan",
        UpdateStatus.MISSING_SKIPPED: "cyan",
        UpdateStatus.UPDATED: "bold green",
        UpdateStatus.FAILED: "bold red",
        UpdateStatus.SKIPPED: "dim",
    }.get(status, "white")


def _status_label(status: UpdateStatus) -> str:
    return {
        UpdateStatus.WILL_CHANGE_MISSING: "📭 WILL CHANGE (MISSING)",
        UpdateStatus.WILL_CHANGE_MISMATCH: "🔄 WILL CHANGE (MISMATCH)",
        UpdateStatus.ALREADY_MATCHES: "✅ ALREADY MATCHES",
        UpdateStatus.NO_VLAB: "⚠️  NO VLAB",
        UpdateStatus.NO_EMAIL_SET: "☢️  NO EMAIL",
        UpdateStatus.MISMATCH_SKIPPED: "⏭️  MISMATCH SKIPPED",
        UpdateStatus.MISSING_SKIPPED: "⏭️  MISSING SKIPPED",
        UpdateStatus.UPDATED: "✅ UPDATED",
        UpdateStatus.FAILED: "❌ FAILED",
        UpdateStatus.SKIPPED: "⏭️  SKIPPED",
    }.get(status, "?")


def display_results(results: List[VLabResult], title: str = "Analysis Results") -> None:
    """Render results as a rich table."""
    table = Table(
        title=f"{title} ({len(results)} entries)",
        header_style="bold cyan",
        row_styles=["", "dim"],
        padding=(0, 1),
        show_lines=True,
    )
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("User ID", no_wrap=True, style="dim", max_width=38)
    table.add_column("VLab ID", no_wrap=True, style="dim", max_width=38)
    table.add_column("VLab Name", min_width=10, max_width=28)
    table.add_column("User Email", min_width=16, max_width=30)
    table.add_column("Current Email", min_width=14, max_width=30)
    table.add_column("→ New Email", min_width=14, max_width=30)
    table.add_column("Status", min_width=14, max_width=18)
    table.add_column("Detail", min_width=20, max_width=50)

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.user_id,
            r.vlab_id,
            r.vlab_name,
            r.user_email,
            r.current_email,
            r.new_email,
            Text(_status_label(r.status), style=_status_style(r.status)),
            r.detail,
        )

    console.print(table)


def display_summary(results: List[VLabResult]) -> None:
    """Show a summary of the results."""
    counts: Dict[UpdateStatus, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines = ["[bold underline]Summary[/]\n"]
    for status in UpdateStatus:
        count = counts.get(status, 0)
        if count > 0:
            lines.append(f"  [{_status_style(status)}]{_status_label(status)}[/]: {count}")

    console.print(Panel("\n".join(lines), border_style="cyan", padding=(1, 2)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    console.print(
        Panel(
            "[bold]Virtual Lab Reference Email Updater[/]\n"
            "[dim]Updates virtual lab reference_email to match owner's email from CSV[/]",
            border_style="bright_blue",
            padding=(1, 4),
        )
    )

    # --- CSV file input ---
    console.print("\n[bold]CSV File[/]")
    csv_path_str = inquirer.filepath(
        message="Path to CSV file (must have 'id' and 'email' columns):",
        validate=lambda p: Path(p).exists() and Path(p).suffix.lower() == ".csv",
        invalid_message="File must exist and have a .csv extension",
    ).execute()

    csv_path = Path(csv_path_str)

    try:
        users = load_csv(csv_path)
    except Exception as e:
        console.print(f"[red]Error reading CSV:[/] {e}")
        return 1

    if not users:
        console.print("[red]No valid rows found in CSV.[/]")
        return 1

    console.print(f"[green]✓ Loaded {len(users)} user(s) from CSV[/]")

    # Show a preview of the first few rows
    if len(users) <= 5:
        preview = users
    else:
        preview = users[:5]

    preview_table = Table(title="CSV Preview", header_style="bold", show_lines=False)
    preview_table.add_column("User ID", style="dim")
    preview_table.add_column("Email")
    for u in preview:
        preview_table.add_row(u["id"], u["email"])
    if len(users) > 5:
        preview_table.add_row("…", f"… and {len(users) - 5} more")
    console.print(preview_table)

    # --- Database connection ---
    console.print("\n[bold]Database Connection[/]")

    db_host = inquirer.text(
        message="PostgreSQL host:",
        default="localhost",
    ).execute()

    db_port = inquirer.text(
        message="PostgreSQL port:",
        default="15432",
    ).execute()

    db_user = inquirer.text(
        message="PostgreSQL user:",
        default="vlm",
    ).execute()

    db_password = inquirer.secret(
        message="PostgreSQL password:",
    ).execute()

    db_name = inquirer.text(
        message="Database name:",
        default="vlm",
    ).execute()

    # Build connection string (synchronous psycopg2)
    connection_string = (
        f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )

    # Validate connection
    console.print("\n[bold]Verifying database connection…[/]")
    try:
        db = DatabaseConnection(connection_string)
        db_info = db.get_db_info()

        console.print(Panel(
            f"[bold green]✅ Connected successfully[/]\n\n"
            f"[bold]Database:[/]      {db_info['database']}\n"
            f"[bold]Version:[/]       {db_info['version'][:60]}\n"
            f"[bold]Active VLabs:[/]  {db_info['active_vlabs']}",
            border_style="green",
            padding=(1, 2),
        ))
    except Exception as e:
        console.print(Panel(
            f"[bold red]❌ Connection failed[/]\n\n"
            f"[bold]Host:[/]      {db_host}:{db_port}\n"
            f"[bold]Database:[/]  {db_name}\n"
            f"[bold]Error:[/]     {e}",
            border_style="red",
            padding=(1, 2),
        ))
        return 1

    # --- Mode selection ---
    mode = inquirer.select(
        message="Execution mode:",
        choices=[
            {"name": "🔍 Dry run (analyze only, no changes)", "value": "dry"},
            {"name": "⚡ Live (analyze + apply changes)", "value": "live"},
        ],
        default="dry",
        pointer="❯",
    ).execute()

    is_dry_run = mode == "dry"

    if is_dry_run:
        console.print(
            Panel(
                "[bold yellow]DRY RUN MODE[/]\n"
                "No changes will be made to the database.\n"
                "This will only show what would happen.",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        scope = UpdateScope.BOTH
    else:
        console.print(
            Panel(
                "[bold red]⚠️  LIVE MODE[/]\n"
                "Changes WILL be applied to the database.\n"
                "Make sure you have verified the CSV and environment.",
                border_style="red",
                padding=(1, 2),
            )
        )

        # --- Update scope selection (live mode only) ---
        update_scope = inquirer.select(
            message="Update scope:",
            choices=[
                {"name": "📭 Only missing — set email where reference_email is empty/null", "value": "missing_only"},
                {"name": "🔄 Only mismatches — overwrite where reference_email differs from CSV", "value": "mismatch_only"},
                {"name": "📭+🔄 Both — update missing AND mismatching emails", "value": "both"},
            ],
            default="missing_only",
            pointer="❯",
        ).execute()

        scope = UpdateScope(update_scope)

    # --- Analysis phase ---
    console.print("\n[bold]Analyzing virtual labs…[/]\n")
    results = analyze_users(db, users, scope)
    display_results(
        results,
        title="Analysis Results (Dry Run)" if is_dry_run else "Analysis Results",
    )
    display_summary(results)

    # Count actionable updates
    actionable = [r for r in results if r.status in (UpdateStatus.WILL_CHANGE_MISSING, UpdateStatus.WILL_CHANGE_MISMATCH)]

    if not actionable:
        console.print(
            "\n[green]No updates needed. All virtual labs already have matching emails or have issues.[/]"
        )
        return 0

    if is_dry_run:
        console.print(
            f"\n[bold yellow]Dry run complete.[/] "
            f"[bold]{len(actionable)}[/] virtual lab(s) would be updated."
        )
        console.print("[dim]Re-run with Live mode to apply changes.[/]")
        return 0

    # --- Confirmation for live mode ---
    console.print(f"\n[bold]{len(actionable)}[/] virtual lab(s) will be updated.")

    confirm = inquirer.confirm(
        message=f"Apply {len(actionable)} update(s) to the database? This cannot be easily undone.",
        default=False,
    ).execute()

    if not confirm:
        console.print("[dim]Aborted. No changes made.[/]")
        return 0

    # Double confirmation for safety
    double_confirm = inquirer.text(
        message=f'Type "UPDATE {len(actionable)}" to confirm:',
    ).execute()

    if double_confirm.strip() != f"UPDATE {len(actionable)}":
        console.print("[dim]Confirmation failed. No changes made.[/]")
        return 0

    # --- Apply updates ---
    console.print("\n[bold]Applying updates…[/]\n")
    final_results = apply_updates(db, results)
    display_results(final_results, title="Final Results")
    display_summary(final_results)

    updated_count = sum(1 for r in final_results if r.status == UpdateStatus.UPDATED)
    failed_count = sum(1 for r in final_results if r.status == UpdateStatus.FAILED)

    console.print(
        f"\n[bold green]{updated_count}[/] updated, "
        f"[bold red]{failed_count}[/] failed "
        f"out of {len(actionable)} attempted."
    )

    return 0 if failed_count == 0 else 1


def run_async() -> int:
    """Entry point for poetry script command."""
    return main()


if __name__ == "__main__":
    sys.exit(main())
