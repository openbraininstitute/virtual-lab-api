#!/usr/bin/env python3
"""
Bulk project deletion script (interactive, phased, dry-run by default).

Supports two modes:
  - soft (default): marks projects as deleted (reversible)
  - hard: permanently removes projects AND all dependent rows (irreversible)

Supports two selection strategies:
  - delete list: provide the project IDs to delete (--project-ids)
  - keep list:   provide the project IDs to KEEP; everything else is deleted (--keep-ids)

Every action is logged to ./deletion-out/ for audit trail.

Usage
-----
  # Dry-run: audit projects, show what would happen
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --project-ids "id1,id2,id3"

  # Apply soft-delete
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --project-ids "id1,id2,id3" \
      --apply

  # Keep only specific projects, delete the rest
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --keep-ids "id_to_keep_1,id_to_keep_2" \
      --apply

  # Apply hard-delete (IRREVERSIBLE — removes rows from DB entirely)
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --project-ids "id1,id2,id3" \
      --hard \
      --apply

  # Read project IDs from a file (one UUID per line)
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --project-ids-file projects_to_delete.txt \
      --hard --apply

  # Keep list from a file
  uv run python scripts/delete_projects.py \
      --virtual-lab-id 00000000-0000-0000-0000-000000000001 \
      --keep-ids-file projects_to_keep.txt \
      --apply

Environment
-----------
  DATABASE_URL — async PostgreSQL URL (reads from .env.local by default)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import load_dotenv
from InquirerPy import inquirer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_labs.infrastructure.db.models import (  # noqa: E402
    Bookmark,
    Project,
    ProjectInvite,
    ProjectStar,
    UserPreference,
    VirtualLab,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

console = Console()
logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)

OUT_DIR = Path("deletion-out")
OUT_DIR.mkdir(exist_ok=True)
RUN_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# A fixed "system" user ID used as deleted_by when running from script.
# In production this would be the admin's KC user ID.
SCRIPT_USER_ID = uuid.UUID("481f8535-bfa4-40f2-87e2-705c299fb2ed")


# ---------------------------------------------------------------------------
# Config & state
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    database_url: str
    virtual_lab_id: uuid.UUID
    project_ids: list[uuid.UUID]
    deleted_by: uuid.UUID
    hard: bool
    apply: bool
    keep_mode: bool  # True = project_ids are IDs to KEEP (delete the rest)

    @property
    def dry_run(self) -> bool:
        return not self.apply

    @property
    def mode_label(self) -> str:
        return "HARD-DELETE" if self.hard else "SOFT-DELETE"

    @property
    def selection_label(self) -> str:
        return "KEEP list (delete everything else)" if self.keep_mode else "DELETE list"


@dataclass
class ProjectInfo:
    id: uuid.UUID
    name: str
    description: str | None
    virtual_lab_name: str
    deleted: bool
    stars_count: int
    bookmarks_count: int
    invites_count: int
    created_at: datetime


@dataclass
class DeletionState:
    audited: list[ProjectInfo] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _banner(title: str, body: str = "", style: str = "bright_blue") -> None:
    console.print(
        Panel(f"[bold]{title}[/]\n{body}".strip(), border_style=style, padding=(1, 2))
    )


def _dump(name: str, payload: Any) -> Path:
    path = OUT_DIR / f"{name}-{RUN_TS}.json"
    path.write_text(json.dumps(payload, default=str, indent=2))
    logger.info(f"   ↳ wrote {path}")
    return path


async def _confirm_phase(name: str, dry_run: bool) -> Literal["yes", "skip", "abort"]:
    suffix = "[DRY-RUN]" if dry_run else "[WILL WRITE]"
    return cast(
        Literal["yes", "skip", "abort"],
        await inquirer.select(
            message=f"{suffix} Proceed with {name}?",
            choices=[
                {"name": "yes — execute this phase", "value": "yes"},
                {"name": "skip — move to the next phase", "value": "skip"},
                {"name": "abort — stop here", "value": "abort"},
            ],
            default="yes",
        ).execute_async(),
    )


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
    table.add_row(
        "Delete type",
        "[red bold]HARD (irreversible, rows removed)[/]"
        if cfg.hard
        else "[yellow]SOFT (reversible, marked deleted)[/]",
    )
    table.add_row(
        "Selection",
        f"[cyan]{cfg.selection_label}[/] ({len(cfg.project_ids)} IDs provided)",
    )
    table.add_row("Database URL", cfg.database_url[:60] + "…")
    table.add_row("Virtual Lab ID", str(cfg.virtual_lab_id))
    table.add_row("Projects to delete", str(len(cfg.project_ids)))
    table.add_row("Deleted-by user", str(cfg.deleted_by))
    console.print(table)

    # DB reachability
    engine = create_async_engine(cfg.database_url, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        logger.info("✅ DB reachable")
    except Exception as e:
        logger.error(f"❌ DB unreachable: {e}")
        raise SystemExit(2)
    finally:
        await engine.dispose()

    # Validate virtual lab exists
    engine = create_async_engine(cfg.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as session:
            vl = (
                await session.execute(
                    select(VirtualLab).where(VirtualLab.id == cfg.virtual_lab_id)
                )
            ).scalar_one_or_none()
            if vl is None:
                logger.error(
                    f"❌ Virtual lab {cfg.virtual_lab_id} not found in database."
                )
                raise SystemExit(2)
            if vl.deleted:
                logger.warning(
                    f"⚠️  Virtual lab '{vl.name}' is already marked as deleted."
                )
            else:
                logger.info(f"✅ Virtual lab found: '{vl.name}'")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Phase 1 — Audit
# ---------------------------------------------------------------------------


async def phase1_audit(cfg: RunConfig, state: DeletionState) -> None:
    _banner(
        "Phase 1 — Audit",
        "Read-only inventory of projects to be deleted.",
    )

    engine = create_async_engine(cfg.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            audit_table = Table(
                title="Projects targeted for deletion",
                header_style="bold cyan",
                padding=(0, 1),
            )
            for col in (
                "Project ID",
                "Name",
                "Already deleted?",
                "Stars",
                "Bookmarks",
                "Invites",
                "Created",
            ):
                audit_table.add_column(col)

            for pid in cfg.project_ids:
                row = (
                    await session.execute(
                        select(Project, VirtualLab)
                        .join(VirtualLab)
                        .where(
                            and_(
                                Project.id == pid,
                                Project.virtual_lab_id == cfg.virtual_lab_id,
                            )
                        )
                    )
                ).one_or_none()

                if row is None:
                    state.skipped.append(
                        {"project_id": str(pid), "reason": "not_found"}
                    )
                    audit_table.add_row(
                        str(pid), "[red]NOT FOUND[/]", "—", "—", "—", "—", "—"
                    )
                    continue

                project, vl = row.tuple()

                stars = (
                    await session.execute(
                        select(func.count(ProjectStar.id)).where(
                            ProjectStar.project_id == pid
                        )
                    )
                ).scalar() or 0

                bookmarks = (
                    await session.execute(
                        select(func.count(Bookmark.id)).where(
                            Bookmark.project_id == pid
                        )
                    )
                ).scalar() or 0

                invites = (
                    await session.execute(
                        select(func.count(ProjectInvite.id)).where(
                            ProjectInvite.project_id == pid
                        )
                    )
                ).scalar() or 0

                info = ProjectInfo(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    virtual_lab_name=vl.name,
                    deleted=project.deleted,
                    stars_count=stars,
                    bookmarks_count=bookmarks,
                    invites_count=invites,
                    created_at=project.created_at,
                )
                state.audited.append(info)

                deleted_str = "[yellow]YES[/]" if project.deleted else "no"
                audit_table.add_row(
                    str(project.id),
                    project.name,
                    deleted_str,
                    str(stars),
                    str(bookmarks),
                    str(invites),
                    project.created_at.strftime("%Y-%m-%d"),
                )

            console.print(audit_table)

            # Summary
            already_deleted = sum(1 for p in state.audited if p.deleted)
            to_delete = sum(1 for p in state.audited if not p.deleted)

            summary = Table(show_header=False, padding=(0, 1))
            summary.add_column("Metric", style="bold")
            summary.add_column("Value")
            summary.add_row("Total requested", str(len(cfg.project_ids)))
            summary.add_row("Found & active", str(to_delete))
            summary.add_row("Already deleted", str(already_deleted))
            summary.add_row("Not found / skipped", str(len(state.skipped)))
            console.print(summary)

    finally:
        await engine.dispose()

    _dump(
        "deletion-audit",
        {
            "virtual_lab_id": str(cfg.virtual_lab_id),
            "audited": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "deleted": p.deleted,
                    "stars": p.stars_count,
                    "bookmarks": p.bookmarks_count,
                    "invites": p.invites_count,
                }
                for p in state.audited
            ],
            "skipped": state.skipped,
        },
    )


# ---------------------------------------------------------------------------
# Phase 2 — Confirmation & Deletion
# ---------------------------------------------------------------------------


async def _soft_delete_project(
    session: AsyncSession,
    project: ProjectInfo,
    cfg: RunConfig,
    state: DeletionState,
) -> None:
    """Soft-delete: set deleted=True, preserve all data."""
    result = await session.execute(
        update(Project)
        .where(
            and_(
                Project.id == project.id,
                Project.virtual_lab_id == cfg.virtual_lab_id,
                ~Project.deleted,
            )
        )
        .values(
            deleted=True,
            deleted_at=func.now(),
            deleted_by=cfg.deleted_by,
        )
        .returning(Project.id, Project.deleted, Project.deleted_at)
    )

    if cfg.dry_run:
        await session.rollback()
        logger.info(f"[DRY-RUN] Would soft-delete: {project.name} ({project.id})")
        state.deleted.append(
            {
                "project_id": str(project.id),
                "name": project.name,
                "mode": "soft",
                "dry_run": True,
            }
        )
    else:
        row = result.one_or_none()
        if row is None:
            logger.warning(
                f"⚠️  {project.name} ({project.id}) — "
                "no rows affected (race condition or already deleted)"
            )
            state.skipped.append(
                {"project_id": str(project.id), "reason": "no_rows_affected"}
            )
        else:
            await session.commit()
            logger.info(
                f"✅ Soft-deleted: {project.name} ({project.id}) at {row.deleted_at}"
            )
            state.deleted.append(
                {
                    "project_id": str(project.id),
                    "name": project.name,
                    "mode": "soft",
                    "deleted_at": str(row.deleted_at),
                }
            )


async def _hard_delete_project(
    session: AsyncSession,
    project: ProjectInfo,
    cfg: RunConfig,
    state: DeletionState,
) -> None:
    """Hard-delete: remove dependent rows first, then the project row.

    Deletion order (respects FK constraints):
      1. UserPreference — NULL-ify the optional project_id FK
      2. ProjectStar    — delete (non-nullable FK)
      3. ProjectInvite  — delete (non-nullable FK)
      4. Bookmark       — delete (non-nullable FK)
      5. Project        — delete the project itself
    """
    pid = project.id
    removed_counts: dict[str, int] = {}

    # 1. Nullify UserPreference.project_id where it points to this project
    res = await session.execute(
        update(UserPreference)
        .where(UserPreference.project_id == pid)
        .values(project_id=None)
    )
    removed_counts["user_preferences_nullified"] = res.rowcount  # type: ignore[assignment]

    # 2. Delete project stars
    res = await session.execute(
        delete(ProjectStar).where(ProjectStar.project_id == pid)
    )
    removed_counts["project_stars"] = res.rowcount  # type: ignore[assignment]

    # 3. Delete project invites
    res = await session.execute(
        delete(ProjectInvite).where(ProjectInvite.project_id == pid)
    )
    removed_counts["project_invites"] = res.rowcount  # type: ignore[assignment]

    # 4. Delete bookmarks
    res = await session.execute(delete(Bookmark).where(Bookmark.project_id == pid))
    removed_counts["bookmarks"] = res.rowcount  # type: ignore[assignment]

    # 5. Delete the project itself
    res = await session.execute(
        delete(Project).where(
            and_(
                Project.id == pid,
                Project.virtual_lab_id == cfg.virtual_lab_id,
            )
        )
    )
    removed_counts["project"] = res.rowcount  # type: ignore[assignment]

    if cfg.dry_run:
        await session.rollback()
        logger.info(
            f"[DRY-RUN] Would hard-delete: {project.name} ({project.id}) "
            f"— cascaded: {removed_counts}"
        )
        state.deleted.append(
            {
                "project_id": str(project.id),
                "name": project.name,
                "mode": "hard",
                "dry_run": True,
                "would_remove": removed_counts,
            }
        )
    else:
        if removed_counts["project"] == 0:
            await session.rollback()
            logger.warning(
                f"⚠️  {project.name} ({project.id}) — "
                "project row not found during hard-delete (race condition?)"
            )
            state.skipped.append(
                {"project_id": str(project.id), "reason": "hard_delete_no_rows"}
            )
        else:
            await session.commit()
            logger.info(
                f"✅ Hard-deleted: {project.name} ({project.id}) "
                f"— removed: {removed_counts}"
            )
            state.deleted.append(
                {
                    "project_id": str(project.id),
                    "name": project.name,
                    "mode": "hard",
                    "removed": removed_counts,
                }
            )


async def phase2_delete(cfg: RunConfig, state: DeletionState) -> None:
    if cfg.hard:
        _banner(
            "Phase 2 — HARD-DELETE projects",
            "Permanently removes project rows AND all dependent data.\n"
            "This is IRREVERSIBLE. Related stars, bookmarks, and invites will be gone.",
        )
    else:
        _banner(
            "Phase 2 — Soft-delete projects",
            "Sets deleted=True on each project. Data is NOT removed from disk.",
        )

    candidates = [p for p in state.audited if not p.deleted]
    if not candidates:
        logger.info("No active projects to delete. Nothing to do.")
        return

    danger_color = "red bold" if cfg.hard else "red"
    action_word = "HARD-DELETE" if cfg.hard else "soft-delete"

    console.print(
        Panel(
            f"[{danger_color}]About to {action_word} "
            f"{len(candidates)} project(s).[/]\n"
            + (
                "Rows will be PERMANENTLY REMOVED from the database. "
                "This cannot be undone without a backup restore."
                if cfg.hard
                else "This sets deleted=True on each project. Data is NOT removed."
            ),
            border_style="red",
            title="⚠️  Danger zone",
        )
    )

    # List them one more time for the operator
    for p in candidates:
        console.print(f"  • {p.name} ({p.id})")

    # Extra confirmation gate for hard-delete
    if cfg.hard and not cfg.dry_run:
        console.print()
        typed = await inquirer.text(
            message=(
                'Type "HARD DELETE" (exactly) to confirm irreversible deletion, '
                "or anything else to abort:"
            ),
        ).execute_async()
        if typed != "HARD DELETE":
            logger.warning("Confirmation text did not match. Aborting.")
            raise SystemExit(0)

    decision = await _confirm_phase(f"Phase 2 — {action_word}", cfg.dry_run)
    if decision == "abort":
        logger.warning("Aborted by operator.")
        raise SystemExit(0)
    if decision == "skip":
        logger.info("Phase 2 skipped.")
        return

    engine = create_async_engine(cfg.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            for project in candidates:
                try:
                    if cfg.hard:
                        await _hard_delete_project(session, project, cfg, state)
                    else:
                        await _soft_delete_project(session, project, cfg, state)
                except Exception as e:
                    await session.rollback()
                    logger.error(
                        f"❌ Failed to delete {project.name} ({project.id}): {e}"
                    )
                    state.errors.append(
                        {
                            "project_id": str(project.id),
                            "name": project.name,
                            "error": str(e),
                        }
                    )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Phase 3 — Summary
# ---------------------------------------------------------------------------


async def phase3_summary(cfg: RunConfig, state: DeletionState) -> None:
    _banner("Phase 3 — Summary")

    summary = Table(show_header=False, padding=(0, 1))
    summary.add_column("Bucket", style="bold")
    summary.add_column("Count")
    summary.add_row("Requested", str(len(cfg.project_ids)))
    summary.add_row("Deleted", str(len(state.deleted)))
    summary.add_row("Skipped (already deleted / not found)", str(len(state.skipped)))
    summary.add_row("Errors", str(len(state.errors)))
    console.print(summary)

    payload = {
        "config": {
            "apply": cfg.apply,
            "mode": cfg.mode_label,
            "virtual_lab_id": str(cfg.virtual_lab_id),
            "deleted_by": str(cfg.deleted_by),
            "project_ids": [str(p) for p in cfg.project_ids],
        },
        "deleted": state.deleted,
        "skipped": state.skipped,
        "errors": state.errors,
    }
    _dump("deletion-summary", payload)

    if state.errors:
        console.print(
            Panel(
                f"[bold red]{len(state.errors)} project(s) failed to delete.[/]\n"
                "Check the deletion-summary JSON for details.",
                border_style="red",
            )
        )

    console.print(
        f"[dim]All artefacts written under {OUT_DIR}/. Keep these as the audit log.[/]"
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _parse_project_ids(raw: str) -> list[uuid.UUID]:
    """Parse comma-separated or newline-separated UUIDs."""
    ids: list[uuid.UUID] = []
    for token in raw.replace(",", "\n").splitlines():
        token = token.strip()
        if not token or token.startswith("#"):
            continue
        try:
            ids.append(uuid.UUID(token))
        except ValueError:
            logger.error(f"Invalid UUID: '{token}'")
            raise SystemExit(2)
    return ids


def _parse_args() -> RunConfig:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(
        description="Bulk delete projects from a virtual lab (soft or hard)."
    )
    parser.add_argument(
        "--virtual-lab-id",
        required=True,
        help="UUID of the virtual lab containing the projects.",
    )
    parser.add_argument(
        "--project-ids",
        default=None,
        help="Comma-separated list of project UUIDs to delete.",
    )
    parser.add_argument(
        "--project-ids-file",
        default=None,
        help="Path to a file with one project UUID per line (projects to delete).",
    )
    parser.add_argument(
        "--keep-ids",
        default=None,
        help="Comma-separated list of project UUIDs to KEEP. "
        "All other projects in the VL will be deleted.",
    )
    parser.add_argument(
        "--keep-ids-file",
        default=None,
        help="Path to a file with one project UUID per line (projects to keep).",
    )
    parser.add_argument(
        "--deleted-by",
        default=None,
        help="UUID of the user performing the deletion (default: system zero-UUID).",
    )
    parser.add_argument(
        "--hard",
        action="store_true",
        help="IRREVERSIBLE hard-delete: removes project rows and all dependent data "
        "from the database entirely. Without this flag, soft-delete is used.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this flag the script is read-only.",
    )
    args = parser.parse_args()

    # Parse virtual lab ID
    try:
        virtual_lab_id = uuid.UUID(args.virtual_lab_id)
    except ValueError:
        logger.error(f"Invalid virtual-lab-id: '{args.virtual_lab_id}'")
        raise SystemExit(2)

    # Parse project IDs — either "delete" list or "keep" list
    has_delete = args.project_ids or args.project_ids_file
    has_keep = args.keep_ids or args.keep_ids_file

    if has_delete and has_keep:
        logger.error(
            "Provide either delete IDs (--project-ids/--project-ids-file) "
            "OR keep IDs (--keep-ids/--keep-ids-file), not both."
        )
        raise SystemExit(2)
    if not has_delete and not has_keep:
        logger.error(
            "Provide --project-ids, --project-ids-file, --keep-ids, or --keep-ids-file."
        )
        raise SystemExit(2)

    keep_mode = bool(has_keep)

    if has_keep:
        # Parse keep IDs
        if args.keep_ids and args.keep_ids_file:
            logger.error("Provide either --keep-ids or --keep-ids-file, not both.")
            raise SystemExit(2)
        if args.keep_ids_file:
            file_path = Path(args.keep_ids_file)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                raise SystemExit(2)
            project_ids = _parse_project_ids(file_path.read_text())
        else:
            project_ids = _parse_project_ids(args.keep_ids)
    else:
        # Parse delete IDs
        if args.project_ids and args.project_ids_file:
            logger.error(
                "Provide either --project-ids or --project-ids-file, not both."
            )
            raise SystemExit(2)
        if args.project_ids_file:
            file_path = Path(args.project_ids_file)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                raise SystemExit(2)
            project_ids = _parse_project_ids(file_path.read_text())
        else:
            project_ids = _parse_project_ids(args.project_ids)

    if not project_ids:
        logger.error("No project IDs provided.")
        raise SystemExit(2)

    # Deleted-by user
    deleted_by = SCRIPT_USER_ID
    if args.deleted_by:
        try:
            deleted_by = uuid.UUID(args.deleted_by)
        except ValueError:
            logger.error(f"Invalid deleted-by UUID: '{args.deleted_by}'")
            raise SystemExit(2)

    database_url = os.getenv("DATABASE_URL") or os.getenv(
        "DATABASE_URI",
        "postgresql+asyncpg://user:pass@host:port/db_name",
    )

    return RunConfig(
        database_url=database_url,
        virtual_lab_id=virtual_lab_id,
        project_ids=project_ids,
        deleted_by=deleted_by,
        hard=bool(args.hard),
        apply=bool(args.apply),
        keep_mode=keep_mode,
    )


async def _resolve_keep_mode(cfg: RunConfig) -> RunConfig:
    """Convert a keep-list into a delete-list by querying all active projects in the VL."""
    engine = create_async_engine(cfg.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with Session() as session:
            all_projects = (
                await session.execute(
                    select(Project.id, Project.name).where(
                        and_(
                            Project.virtual_lab_id == cfg.virtual_lab_id,
                            ~Project.deleted,
                        )
                    )
                )
            ).all()

            all_ids = {row.id for row in all_projects}
            keep_ids = set(cfg.project_ids)

            # Warn about keep IDs that don't exist in this VL
            unknown_keep = keep_ids - all_ids
            if unknown_keep:
                logger.warning(
                    f"⚠️  {len(unknown_keep)} keep-ID(s) not found in this VL "
                    f"(will be ignored): {[str(u) for u in unknown_keep]}"
                )

            delete_ids = sorted(all_ids - keep_ids)

            if not delete_ids:
                logger.info("All projects are in the keep list. Nothing to delete.")
                raise SystemExit(0)

            # Show the resolution
            console.print(
                Panel(
                    f"[bold]Keep-mode resolution:[/]\n"
                    f"  Total active projects in VL: {len(all_ids)}\n"
                    f"  Projects to KEEP: {len(keep_ids & all_ids)}\n"
                    f"  Projects to DELETE: [red]{len(delete_ids)}[/]",
                    border_style="yellow",
                    title="Selection strategy",
                )
            )

            # Show which projects will be kept
            kept_names = [
                f"  ✓ {row.name} ({row.id})"
                for row in all_projects
                if row.id in keep_ids
            ]
            if kept_names:
                console.print("\n  [green]Projects that will be KEPT:[/]")
                for line in kept_names:
                    console.print(line)

            # Show which projects will be deleted
            delete_names = [
                f"  ✗ {row.name} ({row.id})"
                for row in all_projects
                if row.id in set(delete_ids)
            ]
            if delete_names:
                console.print("\n  [red]Projects that will be DELETED:[/]")
                for line in delete_names:
                    console.print(line)

            console.print()

    finally:
        await engine.dispose()

    # Return a new config with resolved delete list and keep_mode=False
    return RunConfig(
        database_url=cfg.database_url,
        virtual_lab_id=cfg.virtual_lab_id,
        project_ids=list(delete_ids),
        deleted_by=cfg.deleted_by,
        hard=cfg.hard,
        apply=cfg.apply,
        keep_mode=False,
    )


async def _amain(cfg: RunConfig) -> int:
    state = DeletionState()

    # Phase 0
    await phase0_preflight(cfg)

    # If keep_mode, resolve the keep list into a delete list
    if cfg.keep_mode:
        cfg = await _resolve_keep_mode(cfg)

    _banner(
        "Ready",
        f"Preflight passed. {len(cfg.project_ids)} project(s) targeted.\n"
        "Press Ctrl-C to abort at any time.",
        style="green",
    )
    if not await inquirer.confirm(
        message="Continue to audit?", default=True
    ).execute_async():
        return 0

    # Phase 1
    await phase1_audit(cfg, state)
    candidates = [p for p in state.audited if not p.deleted]
    if not candidates:
        logger.info("Nothing to delete. Exiting.")
        return 0

    # Phase 2
    await phase2_delete(cfg, state)

    # Phase 3
    await phase3_summary(cfg, state)

    return 1 if state.errors else 0


def run() -> int:
    cfg = _parse_args()
    return asyncio.run(_amain(cfg))


if __name__ == "__main__":
    sys.exit(run())
