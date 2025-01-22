import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.budget_interface import BudgetInterface
from virtual_labs.external.accounting.models import BudgetAssignResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def assign_project_budget(
    virtual_lab_id: UUID4, project_id: UUID4, amount: float
) -> BudgetAssignResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        budget_interface = BudgetInterface(httpx_client, client_token)
        return await budget_interface.assign(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            amount=amount,
        )
