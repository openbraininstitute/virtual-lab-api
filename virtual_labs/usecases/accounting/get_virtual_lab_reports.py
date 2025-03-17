from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import VirtualLabReportsResponse


async def get_virtual_lab_reports(
    virtual_lab_id: UUID4,
    page: int,
    page_size: int,
) -> VirtualLabReportsResponse:
    return await accounting_service.get_virtual_lab_reports(
        virtual_lab_id=virtual_lab_id,
        page=page,
        page_size=page_size,
    )
