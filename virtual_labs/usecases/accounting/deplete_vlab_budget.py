"""Deplete all credits from a virtual lab and its projects.

Called on semester end to zero-out the vlab and all its project credits.

Uses the accounting service's /deplete/vlab endpoint which handles
depleting both the vlab balance and all associated project balances
in a single operation.
"""

from loguru import logger
from pydantic import UUID4

from virtual_labs.infrastructure.settings import settings


async def deplete_vlab_budget(
    *,
    virtual_lab_id: UUID4,
) -> bool:
    """Deplete all remaining credits from a vlab and its projects.

    Returns True on success. Best-effort: logs errors but does not raise.

    TODO: Implement once the accounting service exposes /deplete/vlab.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return False

    # TODO: Call the /deplete/vlab endpoint here.
    logger.warning(
        f"deplete_vlab_budget called for vlab {virtual_lab_id} but "
        f"/deplete/vlab endpoint is not yet implemented"
    )
    return False
