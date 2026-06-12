"""Fund a project: top-up the vlab and assign credits to the project.

Called on seat assignment to credit the student's project.

Uses the accounting service's /grant endpoint which handles topping up
the vlab and assigning to the project in a single operation.
"""

from loguru import logger
from pydantic import UUID4

from virtual_labs.infrastructure.settings import settings


async def fund_project(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    amount: float,
) -> bool:
    """Top-up vlab and assign credits to project. Returns True on success.

    Best-effort: logs errors but does not raise.

    TODO: Implement once the accounting service exposes /grant.
    """
    if settings.ACCOUNTING_BASE_URL is None:
        return False

    # TODO: Call the /grant endpoint here.
    logger.warning(
        f"fund_project called for project {project_id} "
        f"(vlab {virtual_lab_id}, amount {amount}) but /grant endpoint is not yet implemented"
    )
    return False
