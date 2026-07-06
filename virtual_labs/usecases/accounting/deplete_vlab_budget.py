"""Deplete all credits from a virtual lab and its projects.

Called on semester end to zero-out the vlab and all its project credits.

Uses the accounting service's /deplete/virtual-lab endpoint which handles
depleting both the vlab balance and all associated project balances
in a single operation.
"""

from loguru import logger
from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.infrastructure.settings import settings


async def deplete_vlab_budget(
    *,
    virtual_lab_id: UUID4,
) -> float | None:
    """Deplete all remaining credits from a vlab and its projects.

    Returns the total amount depleted, or None on failure.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return None

    try:
        response = await accounting_service.deplete_vlab_budget(virtual_lab_id)
        return float(response.data.total_amount)
    except Exception as exc:
        logger.error(f"deplete_vlab_budget failed for vlab {virtual_lab_id}: {exc}")
        return None
