from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import VlabBalanceResponse


async def get_virtual_lab_balance(
    virtual_lab_id: UUID4,
    include_projects: bool = False,
) -> VlabBalanceResponse:
    return await accounting_service.get_virtual_lab_balance(
        virtual_lab_id=virtual_lab_id,
        include_projects=include_projects,
    )
