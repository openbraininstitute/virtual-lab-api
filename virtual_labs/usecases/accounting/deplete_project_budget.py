"""Deplete all credits from a project account.

Called on seat drop to zero-out the student's project credits.
Returns the balance that was depleted, or None on failure.

TODO: Implement once the accounting service exposes /deplete/project.
"""

from loguru import logger
from pydantic import UUID4

from virtual_labs.infrastructure.settings import settings


async def deplete_project_budget(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> float | None:
    """Deplete all remaining credits from a project.

    Returns the balance that was depleted, or None on failure.

    TODO: Implement once the accounting service exposes /deplete/project.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return None

    # TODO: Call the /deplete/project endpoint here.
    # It should return the amount that was depleted (i.e. the balance before depletion).
    logger.warning(
        f"deplete_project_budget called for project {project_id} "
        f"(vlab {virtual_lab_id}) but /deplete/project endpoint is not yet implemented"
    )
    return None
