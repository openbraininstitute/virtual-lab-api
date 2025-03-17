import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.report_interface import ReportInterface
from virtual_labs.external.accounting.models import ProjectReportsResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def get_project_reports(
    project_id: UUID4, page: int, page_size: int
) -> ProjectReportsResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        report_interface = ReportInterface(httpx_client, client_token)
        return await report_interface.get_project_reports(
            project_id=project_id,
            page=page,
            page_size=page_size,
        )
