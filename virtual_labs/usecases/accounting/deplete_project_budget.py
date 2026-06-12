"""Deplete all credits from a project account.

Called on seat drop to zero-out the student's project credits.

Uses the accounting service's /deplete/project endpoint which handles
zeroing out the project balance in a single operation.
"""

from loguru import logger
from pydantic import UUID4

from virtual_labs.infrastructure.settings import settings


async def deplete_project_budget(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> bool:
    """Deplete all remaining credits from a project.

    Returns True on success. Best-effort: logs errors but does not raise.

    TODO: Implement once the accounting service exposes /deplete/project.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return False

    # TODO: Call the /deplete/project endpoint here.
    logger.warning(
        f"deplete_project_budget called for project {project_id} "
        f"(vlab {virtual_lab_id}) but /deplete/project endpoint is not yet implemented"
    )
    return False
