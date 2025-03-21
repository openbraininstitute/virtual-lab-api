from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import BudgetReverseResponse


async def reverse_project_budget(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    amount: float,
) -> BudgetReverseResponse:
    return await accounting_service.reverse_project_budget(
        virtual_lab_id, project_id, amount
    )
