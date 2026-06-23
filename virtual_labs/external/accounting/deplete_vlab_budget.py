import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.budget_interface import BudgetInterface
from virtual_labs.external.accounting.models import BudgetDepleteVlabResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def deplete_vlab_budget(
    virtual_lab_id: UUID4,
) -> BudgetDepleteVlabResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        budget_interface = BudgetInterface(httpx_client, client_token)
        return await budget_interface.deplete_virtual_lab(
            virtual_lab_id=virtual_lab_id,
        )
