import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.budget_interface import BudgetInterface
from virtual_labs.external.accounting.models import BudgetGrantResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def fund_project_budget(project_id: UUID4, amount: float) -> BudgetGrantResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        budget_interface = BudgetInterface(httpx_client, client_token)
        return await budget_interface.grant(
            project_id=project_id,
            amount=amount,
        )
