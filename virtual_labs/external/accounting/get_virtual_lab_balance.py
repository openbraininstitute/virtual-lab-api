import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.balance_interface import (
    BalanceInterface,
)
from virtual_labs.external.accounting.models import VlabBalanceResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def get_virtual_lab_balance(
    virtual_lab_id: UUID4, include_projects: bool = False
) -> VlabBalanceResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        balance_interface = BalanceInterface(httpx_client, client_token)
        return await balance_interface.get_virtual_lab_balance(
            virtual_lab_id=virtual_lab_id,
            include_projects=include_projects,
        )
