from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import ProjAccountCreationResponse


async def create_project_account(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    name: str,
) -> ProjAccountCreationResponse:
    return await accounting_service.create_project_account(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        name=name,
    )
