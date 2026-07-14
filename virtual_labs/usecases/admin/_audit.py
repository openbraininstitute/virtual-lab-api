"""Audit trail for platform-admin mutations.

Every mutating `/admin` usecase calls `log_admin_action` so operator
actions on other people's resources are reconstructable from logs.
Currently a structured log line; if a DB-backed audit table is added
later, this is the single place to write to it.
"""

from typing import Any

from loguru import logger

from virtual_labs.infrastructure.kc.grant import AuthUserGrants


def log_admin_action(
    actor: AuthUserGrants,
    action: str,
    resource_type: str,
    resource_id: Any,
    **extra: Any,
) -> None:
    logger.bind(admin_audit=True).info(
        f"admin-action actor={actor.id} ({actor.username}) "
        f"action={action} resource={resource_type}:{resource_id}"
        + (f" {extra}" if extra else "")
    )
