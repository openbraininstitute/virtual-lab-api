import httpx
from pydantic import UUID4

from virtual_labs.external.accounting.interfaces.account_interface import (
    AccountInterface,
)
from virtual_labs.external.accounting.models import ProjAccountCreationResponse
from virtual_labs.infrastructure.kc.auth import get_client_token


async def create_project_account(
    virtual_lab_id: UUID4, project_id: UUID4, name: str
) -> ProjAccountCreationResponse:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = get_client_token()
        account_interface = AccountInterface(httpx_client, client_token)
        return await account_interface.create_project_account(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            name=name,
        )
