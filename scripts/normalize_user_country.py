#!/usr/bin/env python3
"""
CLI script to normalize user country attributes in Keycloak.

Converts country values from full names (e.g. "Switzerland") to ISO 3166-1
alpha-2 codes (e.g. "CH") for a given list of user IDs.

Features:
  • Dry-run mode (default) — shows what would change without modifying Keycloak
  • Live mode — actually applies the updates after explicit confirmation
  • Detailed reporting with color-coded status for each user
  • Handles edge cases: missing country, already-a-code, unmapped names

Usage:
    python scripts/normalize_user_country.py
    poetry run normalize-country

Requires:
    poetry add rich InquirerPy
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

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


COUNTRY_JSON_PATH = Path(__file__).resolve().parent.parent / "virtual_labs" / "static" / "country.json"




class CountryMapper:
    """Bidirectional mapping between country names and ISO codes."""

    def __init__(self, json_path: Path) -> None:
        if not json_path.exists():
            raise FileNotFoundError(f"Country JSON not found: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data: List[Dict[str, str]] = json.load(f)

        # name (lowercased) -> code
        self._name_to_code: Dict[str, str] = {}
        # code (uppercased) -> name (for display)
        self._code_to_name: Dict[str, str] = {}
        # all valid codes (uppercased)
        self._valid_codes: set[str] = set()

        for entry in data:
            name = entry["name"]
            code = entry["code"]
            self._name_to_code[name.lower()] = code
            self._code_to_name[code.upper()] = name
            self._valid_codes.add(code.upper())

    def is_valid_code(self, value: str) -> bool:
        """Check if a value is already a valid ISO code."""
        return value.strip().upper() in self._valid_codes

    def name_to_code(self, name: str) -> Optional[str]:
        """Convert a country name to its ISO code. Returns None if not found."""
        return self._name_to_code.get(name.strip().lower())

    def code_to_name(self, code: str) -> Optional[str]:
        """Get the display name for a code."""
        return self._code_to_name.get(code.strip().upper())

    @property
    def valid_codes(self) -> set[str]:
        return self._valid_codes



class UpdateStatus(Enum):
    WILL_UPDATE = "will_update"
    ALREADY_CODE = "already_code"
    NO_COUNTRY = "no_country"
    UNMAPPED = "unmapped"
    UPDATED = "updated"
    FAILED = "failed"
    SKIPPED = "skipped"


class UserResult(NamedTuple):
    user_id: str
    email: str
    name: str
    current_country: str
    resolved_code: str
    status: UpdateStatus
    detail: str


class KeycloakCountryUpdater:
    """Handles fetching and updating user country attributes in Keycloak."""

    def __init__(
        self,
        server_url: str,
        client_id: str,
        client_secret: str,
        realm_name: str,
    ) -> None:
        from keycloak import KeycloakAdmin  # type: ignore[import-untyped]

        self.kc = KeycloakAdmin(
            server_url=server_url,
            client_id=client_id,
            client_secret_key=client_secret,
            realm_name=realm_name,
        )
        logger.info(f"Connected to Keycloak at {server_url} (realm: {realm_name})")

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Fetch a user by ID from Keycloak."""
        return self.kc.get_user(user_id=user_id)

    def update_user_country(self, user_id: str, user_data: Dict[str, Any], new_code: str) -> None:
        """Update the country attribute for a user in Keycloak."""
        attributes = user_data.get("attributes", {}) or {}

        # Preserve existing attributes
        merged_attributes = {
            k: v if isinstance(v, list) else [str(v)] for k, v in attributes.items()
        }
        merged_attributes["country"] = [new_code]

        update_payload: Dict[str, Any] = {
            "email": user_data.get("email"),
            "firstName": user_data.get("firstName"),
            "lastName": user_data.get("lastName"),
            "attributes": merged_attributes,
        }

        self.kc.update_user(user_id=user_id, payload=update_payload)

def analyze_users(
    updater: KeycloakCountryUpdater,
    user_ids: List[str],
    mapper: CountryMapper,
) -> List[UserResult]:
    """
    Fetch each user and determine what action is needed.

    Returns a list of UserResult with the analysis for each user.
    """
    results: List[UserResult] = []

    for user_id in user_ids:
        user_id = user_id.strip()
        if not user_id:
            continue

        try:
            user_data = updater.get_user(user_id)
        except Exception as e:
            results.append(UserResult(
                user_id=user_id,
                email="—",
                name="—",
                current_country="—",
                resolved_code="—",
                status=UpdateStatus.FAILED,
                detail=f"Failed to fetch user: {e}",
            ))
            continue

        email = user_data.get("email", "—") or "—"
        first_name = user_data.get("firstName", "") or ""
        last_name = user_data.get("lastName", "") or ""
        display_name = f"{first_name} {last_name}".strip() or "—"

        # Extract country from attributes
        attributes = user_data.get("attributes", {}) or {}
        country_raw = attributes.get("country", "")
        if isinstance(country_raw, list):
            country_value = country_raw[0] if country_raw else ""
        else:
            country_value = str(country_raw) if country_raw else ""

        # Determine action
        if not country_value:
            results.append(UserResult(
                user_id=user_id,
                email=email,
                name=display_name,
                current_country="(empty)",
                resolved_code="—",
                status=UpdateStatus.NO_COUNTRY,
                detail="No country attribute set",
            ))
        elif mapper.is_valid_code(country_value):
            results.append(UserResult(
                user_id=user_id,
                email=email,
                name=display_name,
                current_country=country_value,
                resolved_code=country_value.upper(),
                status=UpdateStatus.ALREADY_CODE,
                detail="Already an ISO code — no change needed",
            ))
        else:
            code = mapper.name_to_code(country_value)
            if code:
                results.append(UserResult(
                    user_id=user_id,
                    email=email,
                    name=display_name,
                    current_country=country_value,
                    resolved_code=code,
                    status=UpdateStatus.WILL_UPDATE,
                    detail=f'"{country_value}" → "{code}"',
                ))
            else:
                results.append(UserResult(
                    user_id=user_id,
                    email=email,
                    name=display_name,
                    current_country=country_value,
                    resolved_code="—",
                    status=UpdateStatus.UNMAPPED,
                    detail=f'Could not map "{country_value}" to any ISO code',
                ))

    return results


def apply_updates(
    updater: KeycloakCountryUpdater,
    results: List[UserResult],
) -> List[UserResult]:
    """
    Apply the actual updates to Keycloak for users with WILL_UPDATE status.

    Returns a new list with updated statuses.
    """
    final_results: List[UserResult] = []

    for result in results:
        if result.status != UpdateStatus.WILL_UPDATE:
            final_results.append(result)
            continue

        try:
            user_data = updater.get_user(result.user_id)
            updater.update_user_country(result.user_id, user_data, result.resolved_code)
            final_results.append(result._replace(
                status=UpdateStatus.UPDATED,
                detail=f'Updated: "{result.current_country}" → "{result.resolved_code}"',
            ))
        except Exception as e:
            final_results.append(result._replace(
                status=UpdateStatus.FAILED,
                detail=f"Update failed: {e}",
            ))

    return final_results



def _status_style(status: UpdateStatus) -> str:
    return {
        UpdateStatus.WILL_UPDATE: "yellow",
        UpdateStatus.ALREADY_CODE: "green",
        UpdateStatus.NO_COUNTRY: "dim",
        UpdateStatus.UNMAPPED: "red",
        UpdateStatus.UPDATED: "bold green",
        UpdateStatus.FAILED: "bold red",
        UpdateStatus.SKIPPED: "dim",
    }.get(status, "white")


def _status_label(status: UpdateStatus) -> str:
    return {
        UpdateStatus.WILL_UPDATE: "⚡ WILL UPDATE",
        UpdateStatus.ALREADY_CODE: "✅ ALREADY CODE",
        UpdateStatus.NO_COUNTRY: "⚠️  NO COUNTRY",
        UpdateStatus.UNMAPPED: "❌ UNMAPPED",
        UpdateStatus.UPDATED: "✅ UPDATED",
        UpdateStatus.FAILED: "❌ FAILED",
        UpdateStatus.SKIPPED: "⏭️  SKIPPED",
    }.get(status, "?")


def display_results(results: List[UserResult], title: str = "Analysis Results") -> None:
    """Render results as a rich table."""
    table = Table(
        title=f"{title} ({len(results)} users)",
        header_style="bold cyan",
        row_styles=["", "dim"],
        padding=(0, 1),
        show_lines=True,
    )
    table.add_column("#", justify="right", style="bold", width=4)
    table.add_column("User ID", no_wrap=True, style="dim", max_width=38)
    table.add_column("Name", min_width=12, max_width=24)
    table.add_column("Email", min_width=16, max_width=30)
    table.add_column("Current Country", min_width=10, max_width=28)
    table.add_column("→ Code", width=8)
    table.add_column("Status", min_width=14, max_width=18)
    table.add_column("Detail", min_width=20, max_width=50)

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.user_id,
            r.name,
            r.email,
            r.current_country,
            r.resolved_code,
            Text(_status_label(r.status), style=_status_style(r.status)),
            r.detail,
        )

    console.print(table)


def display_summary(results: List[UserResult]) -> None:
    """Show a summary of the results."""
    counts = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines = ["[bold underline]Summary[/]\n"]
    for status in UpdateStatus:
        count = counts.get(status, 0)
        if count > 0:
            lines.append(f"  [{_status_style(status)}]{_status_label(status)}[/]: {count}")

    console.print(Panel("\n".join(lines), border_style="cyan", padding=(1, 2)))

def parse_user_ids(raw_input: str) -> List[str]:
    """
    Parse user IDs from a raw string.

    Supports:
      - Comma-separated
      - Newline-separated
      - Space-separated
      - Mixed delimiters (comma + space)
      - Concatenated UUIDs (36-char segments with no separator)
    """
    import re

    raw_input = raw_input.strip()
    if not raw_input:
        return []

    # Strategy 1: Use regex to find all UUID-shaped strings in the input
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )
    found = uuid_pattern.findall(raw_input)
    if found:
        return found

    # Strategy 2: Try splitting concatenated UUIDs (36 chars each, no separators)
    # Remove any whitespace/commas first
    cleaned = re.sub(r"[\s,]+", "", raw_input)
    if len(cleaned) > 36 and len(cleaned) % 36 == 0:
        ids = [cleaned[i:i+36] for i in range(0, len(cleaned), 36)]
        if all(uid.count("-") == 4 for uid in ids):
            return ids

    # Fallback: treat as single ID
    return [raw_input.strip()] if raw_input.strip() else []


def validate_user_ids(ids: List[str]) -> tuple[List[str], List[str]]:
    """Validate UUID format. Returns (valid_ids, invalid_ids)."""
    import re
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    valid = []
    invalid = []
    for uid in ids:
        if uuid_pattern.match(uid):
            valid.append(uid)
        else:
            invalid.append(uid)
    return valid, invalid


def main() -> int:
    console.print(
        Panel(
            "[bold]Country Attribute Normalizer[/]\n"
            "[dim]Converts country names to ISO 3166-1 alpha-2 codes in Keycloak[/]",
            border_style="bright_blue",
            padding=(1, 4),
        )
    )

    # --- Load country mapping ---
    try:
        mapper = CountryMapper(COUNTRY_JSON_PATH)
        logger.info(f"Loaded {len(mapper.valid_codes)} country codes from {COUNTRY_JSON_PATH.name}")
    except Exception as e:
        console.print(f"[red]Error loading country data:[/] {e}")
        return 1

    # --- Keycloak connection ---
    console.print("\n[bold]Keycloak Connection[/]")

    kc_server = inquirer.text(
        message="Keycloak server URL:",
        default="http://localhost:9090/",
    ).execute()

    kc_realm = inquirer.text(
        message="Realm name:",
        default="obp-realm",
    ).execute()

    kc_client_id = inquirer.text(
        message="Client ID:",
        default="obpapp",
    ).execute()

    kc_client_secret = inquirer.secret(
        message="Client secret:",
    ).execute()

    # Validate connection
    try:
        updater = KeycloakCountryUpdater(
            server_url=kc_server,
            client_id=kc_client_id,
            client_secret=kc_client_secret,
            realm_name=kc_realm,
        )
    except Exception as e:
        console.print(f"[red]Failed to connect to Keycloak:[/] {e}")
        return 1

    # Connection health check
    console.print("\n[bold]Verifying Keycloak connection…[/]")
    try:
        import requests as req

        # Force token acquisition by making a real API call
        users_count = updater.kc.users_count()

        # Now the token should be populated
        kc_version = "unknown"
        try:
            token_data = updater.kc.connection.token
            if token_data and "access_token" in token_data:
                headers = {"Authorization": f"Bearer {token_data['access_token']}"}
                version_url = f"{kc_server.rstrip('/')}/admin/serverinfo"
                version_resp = req.get(version_url, headers=headers, timeout=10)
                if version_resp.status_code == 200:
                    info = version_resp.json()
                    kc_version = info.get("systemInfo", {}).get("version", "unknown")
        except Exception:
            pass  # Version check is best-effort

        console.print(Panel(
            f"[bold green]✅ Connected successfully[/]\n\n"
            f"[bold]Server:[/]       {kc_server}\n"
            f"[bold]Realm:[/]        {kc_realm}\n"
            f"[bold]KC Version:[/]   {kc_version}\n"
            f"[bold]Total Users:[/]  {users_count}",
            border_style="green",
            padding=(1, 2),
        ))
    except Exception as e:
        console.print(Panel(
            f"[bold red]❌ Connection check failed[/]\n\n"
            f"[bold]Server:[/]  {kc_server}\n"
            f"[bold]Realm:[/]   {kc_realm}\n"
            f"[bold]Error:[/]   {e}",
            border_style="red",
            padding=(1, 2),
        ))
        proceed = inquirer.confirm(
            message="Connection check failed. Continue anyway?",
            default=False,
        ).execute()
        if not proceed:
            return 1

    # --- User IDs input ---
    console.print("\n[bold]User IDs[/]")
    console.print("[dim]Paste user IDs (comma-separated, space-separated, or concatenated UUIDs):[/]")

    raw_ids = inquirer.text(
        message="User IDs:",
    ).execute()

    parsed_ids = parse_user_ids(raw_ids)

    if not parsed_ids:
        console.print("[red]No user IDs provided.[/]")
        return 1

    valid_ids, invalid_ids = validate_user_ids(parsed_ids)

    if invalid_ids:
        console.print(f"\n[yellow]⚠️  {len(invalid_ids)} invalid UUID(s) will be skipped:[/]")
        for uid in invalid_ids:
            console.print(f"  [dim]• {uid}[/]")

    if not valid_ids:
        console.print("[red]No valid user IDs to process.[/]")
        return 1

    console.print(f"\n[green]✓ {len(valid_ids)} valid user ID(s) to process[/]")

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
                "No changes will be made to Keycloak.\n"
                "This will only show what would happen.",
                border_style="yellow",
                padding=(1, 2),
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]⚠️  LIVE MODE[/]\n"
                "Changes WILL be applied to Keycloak.\n"
                "Make sure you have verified the user IDs and environment.",
                border_style="red",
                padding=(1, 2),
            )
        )

    # --- Analysis phase ---
    console.print("\n[bold]Analyzing users…[/]\n")
    results = analyze_users(updater, valid_ids, mapper)
    display_results(results, title="Analysis Results (Dry Run)" if is_dry_run else "Analysis Results")
    display_summary(results)

    # Count actionable updates
    actionable = [r for r in results if r.status == UpdateStatus.WILL_UPDATE]

    if not actionable:
        console.print("\n[green]No updates needed. All users are already normalized or have issues.[/]")
        return 0

    if is_dry_run:
        console.print(
            f"\n[bold yellow]Dry run complete.[/] "
            f"[bold]{len(actionable)}[/] user(s) would be updated."
        )
        console.print("[dim]Re-run with Live mode to apply changes.[/]")
        return 0

    # --- Confirmation for live mode ---
    console.print(f"\n[bold]{len(actionable)}[/] user(s) will be updated in Keycloak.")

    confirm = inquirer.confirm(
        message=f"Apply {len(actionable)} update(s) to Keycloak? This cannot be easily undone.",
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
    final_results = apply_updates(updater, results)
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
