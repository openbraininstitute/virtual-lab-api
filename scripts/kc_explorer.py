"""
Keycloak Explorer CLI
=====================
Interactive CLI to navigate Keycloak: users, groups, and token introspection.
Uses the admin client from the project's infrastructure and shows the actual
HTTP requests being made to Keycloak.

Usage:
    poetry run python scripts/kc_explorer.py

Requirements (already in [tool.poetry.group.scripts.dependencies]):
    - rich
    - InquirerPy
"""

import asyncio
import json
import sys
from typing import Any

import httpx
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

from virtual_labs.infrastructure.settings import settings

console = Console()

# ---------------------------------------------------------------------------
# Keycloak connection details (from project settings)
# ---------------------------------------------------------------------------
KC_BASE = settings.KC_SERVER_URI.rstrip("/")
KC_REALM = settings.KC_REALM_NAME
KC_CLIENT_ID = settings.KC_CLIENT_ID
KC_CLIENT_SECRET = settings.KC_CLIENT_SECRET

ADMIN_API = f"{KC_BASE}/admin/realms/{KC_REALM}"
TOKEN_URL = f"{KC_BASE}/realms/{KC_REALM}/protocol/openid-connect/token"
USERINFO_URL = f"{KC_BASE}/realms/{KC_REALM}/protocol/openid-connect/userinfo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def show_request(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    """Display the actual HTTP request being made."""
    req_text = f"[bold cyan]{method}[/] {url}"
    console.print()
    console.print(Panel(req_text, title="🔗 Request", border_style="blue"))
    if headers:
        filtered = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        if filtered:
            console.print(f"  Headers: {json.dumps(filtered, indent=2)}")
    if body:
        console.print(f"  Body: {json.dumps(body, indent=2)}")


def show_response(data: Any, title: str = "Response"):
    """Pretty-print JSON response."""
    formatted = json.dumps(data, indent=2, default=str)
    syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title=f"✅ {title}", border_style="green"))


def show_error(msg: str):
    console.print(f"[bold red]❌ Error:[/] {msg}")


async def get_admin_token(client: httpx.AsyncClient) -> str:
    """Get an admin access token using client credentials."""
    body = {
        "grant_type": "client_credentials",
        "client_id": KC_CLIENT_ID,
        "client_secret": KC_CLIENT_SECRET,
    }
    show_request("POST", TOKEN_URL, body={"grant_type": "client_credentials", "client_id": KC_CLIENT_ID, "client_secret": "***"})
    resp = await client.post(TOKEN_URL, data=body)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    console.print("[dim]  → Token acquired successfully[/]")
    return token


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------
async def list_users(client: httpx.AsyncClient, token: str):
    """List users with pagination."""
    first = 0
    max_results = 20

    url = f"{ADMIN_API}/users?first={first}&max={max_results}&briefRepresentation=true"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    users = resp.json()

    table = Table(title=f"Users (showing first {max_results})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Username", style="green")
    table.add_column("Email", style="yellow")
    table.add_column("Enabled", style="magenta")
    table.add_column("First Name")
    table.add_column("Last Name")

    for u in users:
        table.add_row(
            u.get("id", ""),
            u.get("username", ""),
            u.get("email", ""),
            str(u.get("enabled", "")),
            u.get("firstName", ""),
            u.get("lastName", ""),
        )

    console.print(table)
    console.print(f"[dim]Total returned: {len(users)}[/]")


async def get_user_by_id(client: httpx.AsyncClient, token: str):
    """Fetch full user details by user ID."""
    user_id = await asyncio.to_thread(
        inquirer.text(message="Enter user ID (UUID):").execute
    )
    if not user_id.strip():
        show_error("User ID cannot be empty")
        return

    url = f"{ADMIN_API}/users/{user_id.strip()}"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    if resp.status_code == 404:
        show_error(f"User not found: {user_id}")
        return
    resp.raise_for_status()
    show_response(resp.json(), title="User Details")


async def search_users(client: httpx.AsyncClient, token: str):
    """Search users by username, email, first or last name."""
    query = await asyncio.to_thread(
        inquirer.text(message="Search query (username/email/name):").execute
    )
    if not query.strip():
        show_error("Query cannot be empty")
        return

    url = f"{ADMIN_API}/users?search={query.strip()}&max=25"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    users = resp.json()

    if not users:
        console.print("[yellow]No users found.[/]")
        return

    table = Table(title=f"Search Results for '{query.strip()}'")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Username", style="green")
    table.add_column("Email", style="yellow")
    table.add_column("First Name")
    table.add_column("Last Name")

    for u in users:
        table.add_row(
            u.get("id", ""),
            u.get("username", ""),
            u.get("email", ""),
            u.get("firstName", ""),
            u.get("lastName", ""),
        )

    console.print(table)
    console.print(f"[dim]Total found: {len(users)}[/]")


async def get_user_groups(client: httpx.AsyncClient, token: str):
    """Get all groups a specific user belongs to."""
    user_id = await asyncio.to_thread(
        inquirer.text(message="Enter user ID (UUID):").execute
    )
    if not user_id.strip():
        show_error("User ID cannot be empty")
        return

    url = f"{ADMIN_API}/users/{user_id.strip()}/groups"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    if resp.status_code == 404:
        show_error(f"User not found: {user_id}")
        return
    resp.raise_for_status()
    groups = resp.json()

    table = Table(title=f"Groups for user {user_id.strip()}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Path", style="yellow")

    for g in groups:
        table.add_row(g.get("id", ""), g.get("name", ""), g.get("path", ""))

    console.print(table)
    console.print(f"[dim]Total groups: {len(groups)}[/]")


# ---------------------------------------------------------------------------
# Group operations
# ---------------------------------------------------------------------------
async def list_groups(client: httpx.AsyncClient, token: str):
    """List all groups with count."""
    # First get the count
    count_url = f"{ADMIN_API}/groups/count"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", count_url)

    resp = await client.get(count_url, headers=headers)
    resp.raise_for_status()
    count_data = resp.json()
    console.print(f"[bold]Total groups: {count_data.get('count', count_data)}[/]")

    # Then list groups
    url = f"{ADMIN_API}/groups?first=0&max=50&briefRepresentation=true"
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    groups = resp.json()

    table = Table(title="Groups (first 50)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Path", style="yellow")
    table.add_column("Sub-groups", style="magenta")

    for g in groups:
        sub_count = len(g.get("subGroups", []))
        table.add_row(
            g.get("id", ""),
            g.get("name", ""),
            g.get("path", ""),
            str(sub_count),
        )

    console.print(table)


async def search_groups(client: httpx.AsyncClient, token: str):
    """Search groups by name."""
    query = await asyncio.to_thread(
        inquirer.text(message="Search group name:").execute
    )
    if not query.strip():
        show_error("Query cannot be empty")
        return

    url = f"{ADMIN_API}/groups?search={query.strip()}&max=50"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    groups = resp.json()

    if not groups:
        console.print("[yellow]No groups found.[/]")
        return

    table = Table(title=f"Group Search: '{query.strip()}'")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Path", style="yellow")

    for g in groups:
        table.add_row(g.get("id", ""), g.get("name", ""), g.get("path", ""))

    console.print(table)
    console.print(f"[dim]Total found: {len(groups)}[/]")


async def get_group_members(client: httpx.AsyncClient, token: str):
    """Get members of a specific group."""
    group_id = await asyncio.to_thread(
        inquirer.text(message="Enter group ID (UUID):").execute
    )
    if not group_id.strip():
        show_error("Group ID cannot be empty")
        return

    url = f"{ADMIN_API}/groups/{group_id.strip()}/members"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    if resp.status_code == 404:
        show_error(f"Group not found: {group_id}")
        return
    resp.raise_for_status()
    members = resp.json()

    table = Table(title=f"Members of group {group_id.strip()}")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Username", style="green")
    table.add_column("Email", style="yellow")

    for m in members:
        table.add_row(m.get("id", ""), m.get("username", ""), m.get("email", ""))

    console.print(table)
    console.print(f"[dim]Total members: {len(members)}[/]")


async def get_group_details(client: httpx.AsyncClient, token: str):
    """Get full details of a group by ID."""
    group_id = await asyncio.to_thread(
        inquirer.text(message="Enter group ID (UUID):").execute
    )
    if not group_id.strip():
        show_error("Group ID cannot be empty")
        return

    url = f"{ADMIN_API}/groups/{group_id.strip()}"
    headers = {"Authorization": f"Bearer {token}"}
    show_request("GET", url)

    resp = await client.get(url, headers=headers)
    if resp.status_code == 404:
        show_error(f"Group not found: {group_id}")
        return
    resp.raise_for_status()
    show_response(resp.json(), title="Group Details")


# ---------------------------------------------------------------------------
# Token / UserInfo operations
# ---------------------------------------------------------------------------
async def userinfo_from_token(client: httpx.AsyncClient, _token: str):
    """Fetch userinfo endpoint using a user access token."""
    user_token = await asyncio.to_thread(
        inquirer.text(message="Paste user access token (Bearer token):").execute
    )
    if not user_token.strip():
        show_error("Token cannot be empty")
        return

    headers = {"Authorization": f"Bearer {user_token.strip()}"}
    show_request("GET", USERINFO_URL)

    resp = await client.get(USERINFO_URL, headers=headers)
    if resp.status_code == 401:
        show_error("Token is invalid or expired")
        return
    resp.raise_for_status()
    show_response(resp.json(), title="UserInfo (from token)")


async def introspect_token(client: httpx.AsyncClient, _token: str):
    """Introspect a token to see its claims and validity."""
    user_token = await asyncio.to_thread(
        inquirer.text(message="Paste token to introspect:").execute
    )
    if not user_token.strip():
        show_error("Token cannot be empty")
        return

    introspect_url = f"{KC_BASE}/realms/{KC_REALM}/protocol/openid-connect/token/introspect"
    body = {
        "token": user_token.strip(),
        "client_id": KC_CLIENT_ID,
        "client_secret": KC_CLIENT_SECRET,
    }
    show_request("POST", introspect_url, body={"token": "***", "client_id": KC_CLIENT_ID, "client_secret": "***"})

    resp = await client.post(introspect_url, data=body)
    resp.raise_for_status()
    show_response(resp.json(), title="Token Introspection")


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
MENU_CHOICES = {
    "👤 List users (first 20)": list_users,
    "🔍 Search users": search_users,
    "📋 Get user by ID (full details)": get_user_by_id,
    "📂 Get user's groups": get_user_groups,
    "─────────────────────────────────": None,
    "📁 List groups (with count)": list_groups,
    "🔎 Search groups by name": search_groups,
    "👥 Get group members": get_group_members,
    "📄 Get group details by ID": get_group_details,
    "──────────────────────────────────": None,
    "🎫 UserInfo from user token": userinfo_from_token,
    "🔐 Introspect a token": introspect_token,
    "───────────────────────────────────": None,
    "🚪 Exit": None,
}


async def main():
    console.print(
        Panel(
            Text.from_markup(
                f"[bold]Keycloak Explorer[/]\n"
                f"Server: [cyan]{KC_BASE}[/]\n"
                f"Realm: [green]{KC_REALM}[/]\n"
                f"Client: [yellow]{KC_CLIENT_ID}[/]"
            ),
            border_style="bright_blue",
        )
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Acquire admin token
        try:
            admin_token = await get_admin_token(client)
        except httpx.HTTPStatusError as e:
            show_error(f"Failed to authenticate with Keycloak: {e.response.status_code} - {e.response.text}")
            sys.exit(1)
        except httpx.ConnectError:
            show_error(f"Cannot connect to Keycloak at {KC_BASE}. Is it running?")
            sys.exit(1)

        while True:
            console.print()
            choice = await asyncio.to_thread(
                inquirer.select(
                    message="What would you like to do?",
                    choices=list(MENU_CHOICES.keys()),
                ).execute
            )

            if choice == "🚪 Exit":
                console.print("[dim]Bye![/]")
                break

            handler = MENU_CHOICES.get(choice)
            if handler is None:
                continue

            try:
                await handler(client, admin_token)
            except httpx.HTTPStatusError as e:
                show_error(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                show_error(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
