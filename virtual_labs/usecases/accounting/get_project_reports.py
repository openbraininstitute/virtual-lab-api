from pydantic import UUID4

import virtual_labs.external.accounting as accounting_service
from virtual_labs.external.accounting.models import ProjectReportsResponse


async def get_project_reports(
    project_id: UUID4,
    page: int,
    page_size: int,
) -> ProjectReportsResponse:
    return await accounting_service.get_project_reports(
        project_id=project_id,
        page=page,
        page_size=page_size,
    )
