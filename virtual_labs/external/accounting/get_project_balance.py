import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.balance_interface import (
    BalanceInterface,
)
from virtual_labs.external.accounting.models import ProjBalanceResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def get_project_balance(project_id: UUID4) -> ProjBalanceResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        balance_interface = BalanceInterface(httpx_client, client_token)
        return await balance_interface.get_project_balance(
            project_id=project_id,
        )
