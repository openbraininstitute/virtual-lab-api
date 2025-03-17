from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import VlabAccountCreationResponse


async def create_virtual_lab_account(
    virtual_lab_id: UUID4,
    name: str,
) -> VlabAccountCreationResponse:
    return await accounting_service.create_virtual_lab_account(
        virtual_lab_id=virtual_lab_id,
        name=name,
    )
