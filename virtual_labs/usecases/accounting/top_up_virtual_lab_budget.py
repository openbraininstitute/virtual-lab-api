from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import BudgetTopUpResponse


async def top_up_virtual_lab_budget(
    virtual_lab_id: UUID4,
    amount: float,
) -> BudgetTopUpResponse:
    return await accounting_service.top_up_virtual_lab_budget(virtual_lab_id, amount)
