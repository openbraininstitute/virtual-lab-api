from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import BudgetAssignResponse


async def assign_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    amount: float,
) -> BudgetAssignResponse:
    return await accounting_service.assign_project_budget(
        virtual_lab_id, project_id, amount
    )
