#!/usr/bin/env python3
"""
Create a virtual lab + project with explicit IDs (DB rows only).

Intended for non-production use, e.g. mirroring production IDs into staging so
data-migration scripts can resolve them. NO Keycloak groups, Stripe customer,
subscription or accounting account are created: group columns get unique
placeholder values, so the lab/project is invisible to regular users.

Behaviour
---------
- Lab ID already exists (non-deleted)  -> reused as is.
- Project ID already exists             -> nothing to do (error if it belongs
                                            to a different lab).
- Names are optional; when omitted they are generated from the IDs, with a
  numeric suffix if needed, so they never clash with the unique-name indexes
  (lab name among non-deleted labs, project name per lab).
- Dry-run by default; pass --apply to write.

Usage
-----
  uv run seed-vlab-project \
      --virtual-lab-id 5f8376bf-b84f-4188-8ef5-e1df3d7529b4 \
      --project-id 7d22829c-edc6-4b1d-8ab9-99dd9e511e74 \
      --owner-id <staging-user-uuid> \
      [--lab-name "..."] [--project-name "..."] [--apply]

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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_labs.infrastructure.db.models import Project, VirtualLab  # noqa: E402

logger.configure(
    handlers=[{"sink": sys.stdout, "format": "[{time:HH:mm:ss}] {message}"}]
)

ENTITY = "migration"
NAME_MAX_LEN = 250  # String(250) on both tables


@dataclass
class RunConfig:
    database_url: str
    virtual_lab_id: uuid.UUID
    project_id: uuid.UUID
    owner_id: uuid.UUID
    lab_name: str | None
    project_name: str | None
    apply: bool


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


async def _lab_name_taken(session: AsyncSession, name: str) -> bool:
    stmt = select(VirtualLab.id).where(
        func.lower(VirtualLab.name) == name.lower(), ~VirtualLab.deleted
    )
    return (await session.execute(stmt)).first() is not None


async def _project_name_taken(
    session: AsyncSession, name: str, lab_id: uuid.UUID
) -> bool:
    stmt = select(Project.id).where(
        func.lower(Project.name) == name.lower(),
        Project.virtual_lab_id == lab_id,
        ~Project.deleted,
    )
    return (await session.execute(stmt)).first() is not None


async def _resolve_name(
    session: AsyncSession,
    provided: str | None,
    base: str,
    taken: Callable[[AsyncSession, str], Awaitable[bool]],
) -> str:
    """Provided name must be free; a generated one gets a suffix until free."""
    if provided:
        if len(provided) > NAME_MAX_LEN:
            raise SystemExit(f"Name longer than {NAME_MAX_LEN} chars: '{provided}'")
        if await taken(session, provided):
            raise SystemExit(f"Name already in use: '{provided}'")
        return provided

    candidate, n = base, 1
    while await taken(session, candidate):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def _amain(cfg: RunConfig) -> int:
    engine = create_async_engine(cfg.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with Session() as session:
            # --- Project already there? -------------------------------------
            project = await session.get(Project, cfg.project_id)
            if project is not None:
                if project.virtual_lab_id != cfg.virtual_lab_id:
                    logger.error(
                        f"❌ Project {project.id} exists but belongs to lab "
                        f"{project.virtual_lab_id}, not {cfg.virtual_lab_id}."
                    )
                    return 2
                logger.info(
                    f"✓ Project {project.id} already exists "
                    f"(name='{project.name}', deleted={project.deleted}). Nothing to do."
                )
                return 0

            # --- Lab: reuse or create ---------------------------------------
            lab = await session.get(VirtualLab, cfg.virtual_lab_id)
            if lab is not None and lab.deleted:
                logger.error(f"❌ Lab {lab.id} exists but is soft-deleted.")
                return 2

            if lab is None:
                # One-lab-per-owner is app-level only; a second lab makes the
                # owner's "my lab" lookup (.first(), unordered) ambiguous.
                other = (
                    await session.execute(
                        select(VirtualLab.id).where(
                            VirtualLab.owner_id == cfg.owner_id, ~VirtualLab.deleted
                        )
                    )
                ).first()
                if other:
                    logger.warning(
                        f"⚠ Owner {cfg.owner_id} already owns lab {other[0]}; "
                        "their 'my lab' lookup may return either lab."
                    )

                short = str(cfg.virtual_lab_id)[:8]
                lab = VirtualLab(
                    id=cfg.virtual_lab_id,
                    owner_id=cfg.owner_id,
                    admin_group_id=f"migration-vlab-{cfg.virtual_lab_id}-admin",
                    member_group_id=f"migration-vlab-{cfg.virtual_lab_id}-member",
                    name=await _resolve_name(
                        session, cfg.lab_name, f"migration-lab-{short}", _lab_name_taken
                    ),
                    entity=ENTITY,
                    email_verified=False,
                    deleted=False,
                )
                session.add(lab)
                logger.info(f"+ Lab     {lab.id}  name='{lab.name}'")
            else:
                logger.info(f"✓ Lab     {lab.id}  exists (name='{lab.name}'), reusing")

            # --- Project ----------------------------------------------------
            short = str(cfg.project_id)[:8]

            async def taken(s: AsyncSession, name: str) -> bool:
                return await _project_name_taken(s, name, cfg.virtual_lab_id)

            project = Project(
                id=cfg.project_id,
                virtual_lab_id=cfg.virtual_lab_id,
                owner_id=cfg.owner_id,
                admin_group_id=f"migration-proj-{cfg.project_id}-admin",
                member_group_id=f"migration-proj-{cfg.project_id}-member",
                name=await _resolve_name(
                    session, cfg.project_name, f"migration-project-{short}", taken
                ),
                deleted=False,
            )
            session.add(project)
            logger.info(f"+ Project {project.id}  name='{project.name}'")

            # Flush in both modes so constraint violations surface in dry-run too.
            await session.flush()
            if not cfg.apply:
                await session.rollback()
                logger.info("Dry-run: rolled back. Re-run with --apply to write.")
                return 0
            await session.commit()

        logger.info("✅ Committed.")
    finally:
        await engine.dispose()

    return 0


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid UUID: '{value}'")


def _parse_args() -> RunConfig:
    load_dotenv(".env.local")

    parser = argparse.ArgumentParser(
        description="Create a virtual lab + project with explicit IDs (DB only)."
    )
    parser.add_argument("--virtual-lab-id", required=True, type=_parse_uuid)
    parser.add_argument("--project-id", required=True, type=_parse_uuid)
    parser.add_argument("--owner-id", required=True, type=_parse_uuid)
    parser.add_argument("--lab-name", help="Optional; generated if omitted.")
    parser.add_argument("--project-name", help="Optional; generated if omitted.")
    parser.add_argument(
        "--apply", action="store_true", help="Write (default: dry-run)."
    )
    args = parser.parse_args()

    database_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_URI")
        or "postgresql+asyncpg://user:pass@host:port/db_name"
    )

    return RunConfig(
        database_url=database_url,
        virtual_lab_id=args.virtual_lab_id,
        project_id=args.project_id,
        owner_id=args.owner_id,
        lab_name=(args.lab_name or "").strip() or None,
        project_name=(args.project_name or "").strip() or None,
        apply=args.apply,
    )


def run() -> int:
    cfg = _parse_args()
    return asyncio.run(_amain(cfg))


if __name__ == "__main__":
    sys.exit(run())
