import httpx
from pydantic import UUID4

from virtual_labs.external.nexus.models import NexusOrganization
from virtual_labs.external.nexus.organization_interface import (
    NexusOrganizationInterface,
)
from virtual_labs.infrastructure.kc.auth import get_client_token


async def deprecate_nexus_organization(lab_id: UUID4) -> NexusOrganization:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        client_token = await get_client_token()
        nexus_interface = NexusOrganizationInterface(httpx_client, client_token)
        organization = await nexus_interface.retrieve_organization(lab_id)
        return await nexus_interface.deprecate_organziation(lab_id, organization.rev)
