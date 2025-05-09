import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.budget_interface import BudgetInterface
from virtual_labs.external.accounting.models import BudgetMoveResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def move_project_budget(
    virtual_lab_id: UUID4, debited_from: UUID4, credited_to: UUID4, amount: float
) -> BudgetMoveResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        budget_interface = BudgetInterface(httpx_client, client_token)
        return await budget_interface.move(
            virtual_lab_id=virtual_lab_id,
            debited_from=debited_from,
            credited_to=credited_to,
            amount=amount,
        )
