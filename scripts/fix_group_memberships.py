#!/usr/bin/env python3
"""
Data Migration Script: Fix Virtual Lab and Project Group Memberships

This script ensures data consistency between virtual lab and project Keycloak groups
according to the new business rules:
1. Virtual lab admins should be in ALL project admin groups within that virtual lab
2. Project members should be in the virtual lab's member group (unless they're vlab admins)

Environment Variables (set in .env.local):
    Database:
        POSTGRES_HOST - Database host (default: localhost)
        POSTGRES_PORT - Database port (default: 5432)
        POSTGRES_DB - Database name (default: virtual_labs)
        POSTGRES_USER - Database user (default: postgres)
        POSTGRES_PASSWORD - Database password
    
    SSH Tunnel (optional):
        USE_SSH_TUNNEL - Enable SSH tunnel (true/false, default: false)
        SSH_HOST - SSH host
        SSH_PORT - SSH port (default: 22)
        SSH_USERNAME - SSH username
        SSH_PRIVATE_KEY_PATH - Path to SSH private key (optional)
    
    Keycloak (automatically loaded from project settings):
        KC_SERVER_URL - Keycloak server URL
        KC_CLIENT_ID - Keycloak client ID
        KC_REALM_NAME - Keycloak realm name
        KC_CLIENT_SECRET_KEY - Keycloak client secret

Usage:
    poetry run fix-group-memberships --dry-run
    poetry run fix-group-memberships --execute
    poetry run fix-group-memberships --execute --vlab-id <uuid>
    poetry run fix-group-memberships --execute --verbose
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import asyncssh
import typer
from asyncssh import SSHClientConnection, SSHListener
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from virtual_labs.infrastructure.db.models import Project, VirtualLab
from virtual_labs.repositories.group_repo import GroupQueryRepository
from virtual_labs.repositories.user_repo import UserMutationRepository


load_dotenv(".env.local")


console = Console()


logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


class DatabaseConnection:

    _engine: Optional[AsyncEngine] = None
    _session_maker: Optional[async_sessionmaker[AsyncSession]] = None
    _ssh_tunnel: Optional[SSHListener] = None
    _ssh_conn: Optional[SSHClientConnection] = None

    def __init__(self) -> None:
        self.db_host = os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.db_name = os.getenv("POSTGRES_DB", "virtual_labs")
        self.db_user = os.getenv("POSTGRES_USER", "postgres")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "")
        self.ssh_host = os.getenv("SSH_HOST")
        self.ssh_port = int(os.getenv("SSH_PORT", "22"))
        self.ssh_user = os.getenv("SSH_USERNAME")
        self.ssh_key_path = os.getenv("SSH_PRIVATE_KEY_PATH")
        self.use_ssh = os.getenv("USE_SSH_TUNNEL", "false").lower() == "true"

    async def __aenter__(self) -> "DatabaseConnection":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Establish database connection with optional SSH tunnel"""
        if self.use_ssh and self.ssh_host and self.ssh_user:
            logger.info(f"Establishing SSH tunnel to {self.ssh_host}...")
            
            ssh_options: Dict[str, Any] = {
                "port": self.ssh_port,
                "username": self.ssh_user,
                "known_hosts": None,
            }
            
            if self.ssh_key_path:
                ssh_options["client_keys"] = [self.ssh_key_path]
                logger.debug(f"Using SSH key: {self.ssh_key_path}")
            
            self._ssh_conn = await asyncssh.connect(
                self.ssh_host,
                **ssh_options,
            )
            self._ssh_tunnel = await self._ssh_conn.forward_local_port(
                "", 0, self.db_host, self.db_port
            )
            local_port = self._ssh_tunnel.get_port()
            logger.info(f"SSH tunnel established on local port {local_port}")
            db_url = f"postgresql+asyncpg://{self.db_user}:{self.db_password}@localhost:{local_port}/{self.db_name}"
        else:
            db_url = f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

        self._engine = create_async_engine(db_url, echo=False)
        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Database connection established")

    async def disconnect(self) -> None:
        """Close database connection and SSH tunnel"""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connection closed")

        if self._ssh_tunnel:
            self._ssh_tunnel.close()
            await self._ssh_tunnel.wait_closed()
            logger.info("SSH tunnel closed")

        if self._ssh_conn:
            self._ssh_conn.close()
            await self._ssh_conn.wait_closed()

    def get_session(self) -> AsyncSession:
        """Get a new database session"""
        if not self._session_maker:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_maker()


class MigrationStats:

    def __init__(self) -> None:
        self.total_vlabs: int = 0
        self.total_projects: int = 0
        self.vlab_admins_added_to_projects: int = 0
        self.project_users_added_to_vlab: int = 0
        self.errors: List[str] = []
        self.skipped_users: List[str] = []
        self.start_time: datetime = datetime.now()

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        logger.error(error)

    def add_skip(self, reason: str) -> None:
        self.skipped_users.append(reason)
        logger.warning(reason)

    def get_duration(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def print_summary(self) -> None:
        console.print("\n")
        console.rule("[bold blue]Migration Summary Report[/bold blue]")

        # Create summary table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")

        table.add_row("Virtual Labs Processed", str(self.total_vlabs))
        table.add_row("Projects Processed", str(self.total_projects))
        table.add_row(
            "VLab Admins Added to Projects", str(self.vlab_admins_added_to_projects)
        )
        table.add_row(
            "Project Users Added to VLab", str(self.project_users_added_to_vlab)
        )
        table.add_row("Total Operations", str(self.get_total_operations()))
        table.add_row("Errors", str(len(self.errors)), style="red" if self.errors else "green")
        table.add_row("Skipped Operations", str(len(self.skipped_users)))
        table.add_row("Duration (seconds)", f"{self.get_duration():.2f}")

        console.print(table)

        if self.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for error in self.errors[:10]:  # Show first 10 errors
                console.print(f"  • {error}", style="red")
            if len(self.errors) > 10:
                console.print(
                    f"  ... and {len(self.errors) - 10} more errors", style="red dim"
                )

        if self.skipped_users and len(self.skipped_users) <= 5:
            console.print("\n[bold yellow]Skipped Operations:[/bold yellow]")
            for skip in self.skipped_users:
                console.print(f"  • {skip}", style="yellow")

        console.print("\n")

    def get_total_operations(self) -> int:
        return self.vlab_admins_added_to_projects + self.project_users_added_to_vlab


class GroupMembershipFixer:
    """Main class to fix group memberships"""

    def __init__(
        self, db_conn: DatabaseConnection, dry_run: bool = False, verbose: bool = False
    ) -> None:
        self.db_conn = db_conn
        self.dry_run = dry_run
        self.verbose = verbose
        self.stats = MigrationStats()
        self.gqr = GroupQueryRepository()
        self.umr = UserMutationRepository()

    async def get_all_virtual_labs(self) -> List[VirtualLab]:
        """Fetch all non-deleted virtual labs from database"""
        async with self.db_conn.get_session() as session:
            query = select(VirtualLab).where(~VirtualLab.deleted)
            result = await session.execute(query)
            vlabs = list(result.scalars().all())
            self.stats.total_vlabs = len(vlabs)
            logger.info(f"Found {len(vlabs)} virtual labs")
            return vlabs

    async def get_projects_for_vlab(self, vlab_id: UUID) -> List[Project]:
        """Fetch all non-deleted projects for a virtual lab"""
        async with self.db_conn.get_session() as session:
            query = select(Project).where(
                Project.virtual_lab_id == vlab_id, ~Project.deleted
            )
            result = await session.execute(query)
            projects = list(result.scalars().all())
            self.stats.total_projects += len(projects)
            return projects

    async def get_group_members(self, group_id: str) -> Set[str]:
        """Get all user IDs in a Keycloak group"""
        try:
            user_ids = await self.gqr.a_retrieve_group_user_ids(group_id=group_id)
            return set(user_ids)
        except Exception as e:
            error_msg = f"Failed to get members for group {group_id}: {e}"
            self.stats.add_error(error_msg)
            return set()

    async def add_user_to_group(
        self, user_id: str, group_id: str, description: str
    ) -> bool:
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would add user {user_id} to {description}")
                return True

            await self.umr.a_attach_user_to_group(
                user_id=UUID(user_id), group_id=group_id
            )
            if self.verbose:
                logger.info(f"✓ Added user {user_id} to {description}")
            return True
        except Exception as e:
            error_msg = f"Failed to add user {user_id} to {description}: {e}"
            self.stats.add_error(error_msg)
            return False

    async def fix_vlab_admins_in_projects(
        self, vlab: VirtualLab, projects: List[Project]
    ) -> int:
        """
        fix discrepancy 1: ensure all vlab admins are in all project admin groups
        returns number of users added
        """
        if not projects:
            return 0

        vlab_admin_users = await self.get_group_members(str(vlab.admin_group_id))
        if not vlab_admin_users:
            logger.debug(f"No admin users found for vlab {vlab.id}")
            return 0

        vlab_admin_users.discard(str(vlab.owner_id))

        added_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"Fixing vlab admins for {len(projects)} projects...", total=len(projects)
            )

            for project in projects:
                project_admin_users = await self.get_group_members(
                    project.admin_group_id
                )
                missing_users = vlab_admin_users - project_admin_users

                for user_id in missing_users:
                    success = await self.add_user_to_group(
                        user_id=user_id,
                        group_id=project.admin_group_id,
                        description=f"project {project.name} admin group",
                    )
                    if success:
                        added_count += 1

                progress.advance(task)

        return added_count

    async def fix_project_users_in_vlab(
        self, vlab: VirtualLab, projects: List[Project]
    ) -> int:
        """
        fix discrepancy 2: ensure all project users are in vlab member group
        returns number of users added
        """
        if not projects:
            return 0    

        vlab_admin_users = await self.get_group_members(str(vlab.admin_group_id))
        vlab_member_users = await self.get_group_members(str(vlab.member_group_id))

        added_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"Fixing project users for vlab {vlab.name}...", total=len(projects)
            )

            for project in projects:
                project_admin_users = await self.get_group_members(
                    project.admin_group_id
                )
                project_member_users = await self.get_group_members(
                    project.member_group_id
                )
                all_project_users = project_admin_users | project_member_users

                all_project_users.discard(str(project.owner_id))

                for user_id in all_project_users:
                    if user_id in vlab_admin_users:
                        continue

                    if user_id in vlab_member_users:
                        continue

                    success = await self.add_user_to_group(
                        user_id=user_id,
                        group_id=str(vlab.member_group_id),
                        description=f"vlab {vlab.name} member group",
                    )
                    if success:
                        added_count += 1
                        vlab_member_users.add(user_id)  

                progress.advance(task)

        return added_count

    async def process_virtual_lab(self, vlab: VirtualLab) -> Tuple[int, int]:
        """
        Process a single virtual lab
        Returns: (admins_added_to_projects, project_users_added_to_vlab)
        """
        logger.info(f"\nProcessing Virtual Lab: {vlab.name} ({vlab.id})")

        projects = await self.get_projects_for_vlab(vlab.id)

        if not projects:
            logger.info(f"  No projects found for vlab {vlab.name}")
            return 0, 0

        logger.info(f"  Found {len(projects)} projects")

        # fix discrepancy 1: ensure all vlab admins are in all project admin groups
        admins_added = await self.fix_vlab_admins_in_projects(vlab, projects)
        logger.info(f"  ✓ Added {admins_added} vlab admin memberships to projects")

        # fix discrepancy 2: ensure all project users are in vlab member group
        users_added = await self.fix_project_users_in_vlab(vlab, projects)
        logger.info(f"  ✓ Added {users_added} project user memberships to vlab")

        return admins_added, users_added

    async def run(self, vlab_id: Optional[str] = None) -> None:
        mode = "[bold yellow]DRY RUN MODE[/bold yellow]" if self.dry_run else "[bold green]EXECUTION MODE[/bold green]"
        console.print(f"\n🚀 Starting migration in {mode}\n")

        if vlab_id:
            logger.info(f"Processing specific virtual lab: {vlab_id}")
            async with self.db_conn.get_session() as session:
                try:
                    vlab_uuid = UUID(vlab_id)
                    result = await session.get(VirtualLab, vlab_uuid)
                    if not result:
                        console.print(f"[red]Virtual lab {vlab_id} not found![/red]")
                        return
                    vlabs = [result]
                    self.stats.total_vlabs = 1
                except ValueError:
                    console.print(f"[red]Invalid UUID format: {vlab_id}[/red]")
                    return
        else:
            vlabs = await self.get_all_virtual_labs()

        if not vlabs:
            console.print("[yellow]No virtual labs found to process[/yellow]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            main_task = progress.add_task(
                "Processing virtual labs...", total=len(vlabs)
            )

            for vlab in vlabs:
                try:
                    admins_added, users_added = await self.process_virtual_lab(vlab)
                    self.stats.vlab_admins_added_to_projects += admins_added
                    self.stats.project_users_added_to_vlab += users_added
                except Exception as e:
                    error_msg = f"Error processing vlab {vlab.name} ({vlab.id}): {e}"
                    self.stats.add_error(error_msg)

                progress.advance(main_task)

        self.stats.print_summary()

        if self.dry_run:
            console.print(
                "\n[yellow]⚠️  This was a DRY RUN. No changes were made.[/yellow]"
            )
            console.print(
                "[yellow]Run without --dry-run to execute the changes.[/yellow]\n"
            )


app = typer.Typer(
    name="fix-group-memberships",
    help="Fix Virtual Lab and Project Keycloak group memberships",
    add_completion=False,
)


@app.command()
def run(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Preview changes without executing them (default: True)",
    ),
    vlab_id: Optional[str] = typer.Option(
        None,
        "--vlab-id",
        help="Process only a specific virtual lab ID",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    fix group membership discrepancies between virtual labs and projects.

    This script ensures:
    1. all virtual lab admins are added to all project admin groups within that vlab
    2. all project users (admin/member) are added to the virtual lab member group
    """
    asyncio.run(run_migration(dry_run=dry_run, vlab_id=vlab_id, verbose=verbose))


async def run_migration(
    dry_run: bool = True, vlab_id: Optional[str] = None, verbose: bool = False
) -> None:
    async with DatabaseConnection() as db_conn:
        fixer = GroupMembershipFixer(db_conn, dry_run=dry_run, verbose=verbose)
        await fixer.run(vlab_id=vlab_id)


def run_async() -> None:
    app()


if __name__ == "__main__":
    app()

