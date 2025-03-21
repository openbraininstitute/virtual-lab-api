from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import BudgetMoveResponse


async def move_project_budget(
    virtual_lab_id: UUID4,
    debited_from: UUID4,
    credited_to: UUID4,
    amount: float,
) -> BudgetMoveResponse:
    return await accounting_service.move_project_budget(
        virtual_lab_id, debited_from, credited_to, amount
    )
