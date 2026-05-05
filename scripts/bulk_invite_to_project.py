#!/usr/bin/env python3
"""
Interactive CLI to send bulk project invitations.

Supports two modes:
  • Single user  – enter name + email interactively
  • CSV file     – provide a CSV with columns: name, email

Shared parameters (project_id, virtual_lab_id, inviter_id, role)
are collected once and applied to every invitation.

For each user the script:
  1. Creates (or reuses) a ProjectInvite row in the database
  2. Sends the invite email with a signed JWT link

Usage:
    poetry run bulk-invite
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path
from typing import List, NamedTuple
from uuid import UUID

from InquirerPy import inquirer
from InquirerPy.validator import PathValidator
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Invitee(NamedTuple):
    name: str
    email: str


def _validate_uuid(val: str) -> bool | str:
    try:
        UUID(val)
        return True
    except ValueError:
        return "Must be a valid UUID"


def _validate_email(val: str) -> bool | str:
    if "@" in val and "." in val.split("@")[-1]:
        return True
    return "Must be a valid email address"


def _read_csv(path: str) -> List[Invitee]:
    """Read a CSV with columns: name, email. Returns list of Invitee."""
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if file.suffix.lower() != ".csv":
        raise ValueError(f"Expected a .csv file, got: {file.suffix}")

    invitees: List[Invitee] = []
    # Try utf-8 first, fall back to latin-1 for files exported from Excel/Outlook
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(file, newline="", encoding=encoding) as f:
                f.read()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Could not decode {file.name} with utf-8, latin-1, or cp1252")

    with open(file, newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header row")

        # Normalise headers (strip whitespace, lowercase)
        headers = [h.strip().lower() for h in reader.fieldnames]
        if "email" not in headers:
            raise ValueError(
                f"CSV must have an 'email' column. Found columns: {reader.fieldnames}"
            )
        if "name" not in headers:
            raise ValueError(
                f"CSV must have a 'name' column. Found columns: {reader.fieldnames}"
            )

        for i, row in enumerate(reader, start=2):
            normalised = {k.strip().lower(): v.strip() for k, v in row.items()}
            email = normalised.get("email", "")
            name = normalised.get("name", "")
            if not email:
                logger.warning(f"Row {i}: skipping — empty email")
                continue
            invitees.append(Invitee(name=name, email=email))

    if not invitees:
        raise ValueError("CSV contained no valid rows")
    return invitees



# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def process_invitations(
    *,
    project_id: UUID,
    virtual_lab_id: UUID,
    inviter_id: UUID,
    inviter_name: str,
    role: str,
    invitees: List[Invitee],
    database_url: str,
) -> None:
    """Create invite rows and send emails for each invitee."""
    # Late imports so the CLI stays responsive and we only load heavy deps when needed
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from virtual_labs.core.types import UserRoleEnum
    from virtual_labs.infrastructure.email.invite_email import EmailDetails, send_invite
    from virtual_labs.repositories.invite_repo import (
        InviteMutationRepository,
        InviteQueryRepository,
    )
    from virtual_labs.repositories.project_repo import ProjectQueryRepository

    user_role = UserRoleEnum.admin if role == "admin" else UserRoleEnum.member

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, autoflush=False, autocommit=False, expire_on_commit=False)

    results_table = Table(title="Invitation Results", show_lines=True)
    results_table.add_column("#", style="dim", width=4)
    results_table.add_column("Name", min_width=15)
    results_table.add_column("Email", min_width=25)
    results_table.add_column("Invite ID", min_width=36)
    results_table.add_column("Status", min_width=10)

    async with session_factory() as session:
        session: AsyncSession

        # Validate project + virtual lab exist
        pqr = ProjectQueryRepository(session)
        try:
            project, virtual_lab = await pqr.retrieve_one_project_strict(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
            )
        except Exception as exc:
            console.print(f"[red]Error:[/] Could not find project/virtual lab — {exc}")
            await engine.dispose()
            return

        project_name = str(project.name)
        lab_name = str(virtual_lab.name)
        lab_id = virtual_lab.id

        console.print(
            Panel(
                f"[bold]Lab:[/] {lab_name}\n[bold]Project:[/] {project_name}\n"
                f"[bold]Role:[/] {role}\n[bold]Invitees:[/] {len(invitees)}",
                title="Sending invitations",
                border_style="bright_blue",
            )
        )

        iqr = InviteQueryRepository(session)
        imr = InviteMutationRepository(session)

        for idx, invitee in enumerate(invitees, start=1):
            status = "[green]sent[/]"
            invite_id_str = "—"
            try:
                # Check for existing invite
                existing = await iqr.get_project_invite_by_params(
                    project_id=project_id,
                    email=invitee.email,
                    role=user_role,
                )

                if existing is not None:
                    # Reset to pending and re-send
                    await imr.update_project_invite(
                        invite_id=existing.id,
                        properties={"accepted": False},
                    )
                    invite_id = existing.id
                else:
                    invite = await imr.add_project_invite(
                        project_id=project_id,
                        inviter_id=inviter_id,
                        invitee_role=user_role,
                        invitee_email=invitee.email,
                    )
                    invite_id = invite.id

                invite_id_str = str(invite_id)

                await send_invite(
                    payload=EmailDetails(
                        recipient=invitee.email,
                        invite_id=invite_id,
                        inviter_name=inviter_name,
                        lab_id=lab_id,
                        lab_name=lab_name,
                        project_id=project_id,
                        project_name=project_name,
                    )
                )
            except TimeoutError:
                # SES accepted the email but the SMTP response timed out — treat as sent
                status = "[yellow]sent (timeout warning)[/]"
                logger.warning(f"Timeout after sending to {invitee.email} — email likely delivered")
            except Exception as exc:
                if "timed out" in str(exc).lower():
                    status = "[yellow]sent (timeout warning)[/]"
                    logger.warning(f"Timeout after sending to {invitee.email} — email likely delivered")
                else:
                    status = f"[red]failed: {exc}[/]"
                    logger.error(f"Failed for {invitee.email}: {exc}")

            results_table.add_row(str(idx), invitee.name, invitee.email, invite_id_str, status)

    console.print(results_table)
    await engine.dispose()
    console.print("[bold green]Done.[/]")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _display_csv(invitees: List[Invitee]) -> None:
    """Render the CSV contents as a rich table."""
    table = Table(title=f"CSV Preview ({len(invitees)} rows)", show_lines=True)
    table.add_column("#", style="dim", width=5)
    table.add_column("Name", min_width=20)
    table.add_column("Email", min_width=30)
    for idx, inv in enumerate(invitees, start=1):
        table.add_row(str(idx), inv.name, inv.email)
    console.print(table)


def _prompt_csv_path() -> List[Invitee]:
    """Ask for a CSV path and return parsed invitees."""
    csv_path = inquirer.filepath(
        message="Path to CSV file:",
        validate=PathValidator(is_file=True, message="Must be a valid file path"),
    ).execute()
    return _read_csv(csv_path)


def _validate_positive_int(val: str) -> bool | str:
    try:
        n = int(val)
        return True if n > 0 else "Must be > 0"
    except ValueError:
        return "Must be a number"


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import os

    console.print(
        Panel(
            "[bold]Bulk Project Invitation Tool[/]",
            border_style="bright_blue",
            padding=(1, 4),
        )
    )

    # --- Top-level action ---
    action = inquirer.select(
        message="What would you like to do?",
        choices=[
            {"name": "Explore CSV file", "value": "explore"},
            {"name": "Invite to project", "value": "invite"},
        ],
        pointer="❯",
    ).execute()

    # ---- Explore CSV ----
    if action == "explore":
        try:
            invitees = _prompt_csv_path()
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]Error reading CSV:[/] {exc}")
            return 1
        _display_csv(invitees)
        return 0

    # ---- Invite to project ----
    database_url = inquirer.text(
        message="Database URL (postgresql+asyncpg://…):",
        default="postgresql+asyncpg://vlm:vlm@localhost:15432/vlm",
        validate=lambda v: v.startswith("postgresql") or "Must be a PostgreSQL URL",
    ).execute()

    # Ensure the async driver is in the URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    deployment_namespace = inquirer.text(
        message="Deployment namespace:",
        default="https://openbrainplatform.org",
    ).execute()
    os.environ["DEPLOYMENT_NAMESPACE"] = deployment_namespace

    virtual_lab_id = inquirer.text(
        message="Virtual Lab ID (UUID):",
        validate=_validate_uuid,
    ).execute()

    project_id = inquirer.text(
        message="Project ID (UUID):",
        validate=_validate_uuid,
    ).execute()

    inviter_id = inquirer.text(
        message="Inviter user ID (UUID):",
        validate=_validate_uuid,
    ).execute()

    inviter_name = inquirer.text(
        message="Inviter display name (shown in email):",
        validate=lambda v: len(v.strip()) > 0 or "Name cannot be empty",
    ).execute()

    role = inquirer.select(
        message="Role for invitees:",
        choices=["admin", "member"],
        default="member",
        pointer="❯",
    ).execute()

    # --- Source selection ---
    mode = inquirer.select(
        message="Invitation source:",
        choices=[
            {"name": "Single user", "value": "single"},
            {"name": "CSV file", "value": "csv"},
        ],
        pointer="❯",
    ).execute()

    invitees: List[Invitee] = []

    if mode == "single":
        name = inquirer.text(
            message="Invitee name:",
            validate=lambda v: len(v.strip()) > 0 or "Name cannot be empty",
        ).execute()
        email = inquirer.text(
            message="Invitee email:",
            validate=_validate_email,
        ).execute()
        invitees = [Invitee(name=name.strip(), email=email.strip())]
    else:
        try:
            invitees = _prompt_csv_path()
            console.print(f"[green]Loaded {len(invitees)} invitee(s) from CSV[/]")
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]Error reading CSV:[/] {exc}")
            return 1

    # --- Batch configuration ---
    batch_size_str = inquirer.text(
        message=f"Batch size (total {len(invitees)}, enter to send all at once):",
        default=str(len(invitees)),
        validate=_validate_positive_int,
    ).execute()
    batch_size = int(batch_size_str)

    send_mode = "all"
    if batch_size < len(invitees):
        send_mode = inquirer.select(
            message="Send mode:",
            choices=[
                {"name": "All batches automatically (no pause)", "value": "all"},
                {"name": "Wait for confirmation between batches", "value": "loop"},
            ],
            pointer="❯",
        ).execute()

    # --- Confirmation ---
    total = len(invitees)
    batch_desc = (
        f"all {total} at once"
        if batch_size >= total
        else f"in batches of {batch_size} ({'auto' if send_mode == 'all' else 'manual confirm'})"
    )
    confirm = inquirer.confirm(
        message=f"Send {total} invitation(s) as {role} — {batch_desc}?",
        default=False,
    ).execute()

    if not confirm:
        console.print("[dim]Aborted.[/]")
        return 0

    # --- Send in batches ---
    shared = dict(
        project_id=UUID(project_id),
        virtual_lab_id=UUID(virtual_lab_id),
        inviter_id=UUID(inviter_id),
        inviter_name=inviter_name.strip(),
        role=role,
        database_url=database_url,
    )

    batches = [invitees[i : i + batch_size] for i in range(0, total, batch_size)]

    for batch_num, batch in enumerate(batches, start=1):
        console.print(
            f"\n[bold cyan]Batch {batch_num}/{len(batches)}[/] "
            f"({len(batch)} invitee{'s' if len(batch) != 1 else ''})"
        )
        asyncio.run(process_invitations(invitees=batch, **shared))

        if send_mode == "loop" and batch_num < len(batches):
            proceed = inquirer.confirm(
                message=f"Send next batch ({batch_num + 1}/{len(batches)})?",
                default=True,
            ).execute()
            if not proceed:
                console.print("[dim]Stopped by user.[/]")
                return 0

    return 0


def run_async() -> int:
    """Entry point for poetry script command."""
    return main()
