from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import ProjBalanceResponse


async def get_project_balance(
    project_id: UUID4,
) -> ProjBalanceResponse:
    return await accounting_service.get_project_balance(
        project_id=project_id,
    )
