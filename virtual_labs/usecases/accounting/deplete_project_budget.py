"""Deplete all credits from a project account.

Called on seat drop to zero-out the student's project credits.
Returns the balance that was depleted, or None on failure.

Uses the accounting service's /deplete/project endpoint.
"""

from loguru import logger
from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.infrastructure.settings import settings


async def deplete_project_budget(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> float | None:
    """Deplete all remaining credits from a project.

    Returns the balance that was depleted, or None on failure.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return None

    try:
        response = await accounting_service.deplete_project_budget(project_id)
        return float(response.data.total_amount)
    except Exception as exc:
        logger.error(
            f"deplete_project_budget failed for project {project_id} "
            f"(vlab {virtual_lab_id}): {exc}"
        )
        return None
