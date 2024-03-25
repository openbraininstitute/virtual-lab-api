import httpx
from pydantic import UUID4

from virtual_labs.external.nexus.models import NexusOrganization
from virtual_labs.external.nexus.organization_interface import (
    NexusOrganizationInterface,
)
from virtual_labs.infrastructure.kc.models import AuthUser


async def deprecate_nexus_organization(
    lab_id: UUID4, auth: tuple[AuthUser, str]
) -> NexusOrganization:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport, verify=False) as httpx_client:
        nexus_interface = NexusOrganizationInterface(httpx_client, auth)
        organization = await nexus_interface.retrieve_organization(lab_id)
        return await nexus_interface.deprecate_organziation(lab_id, organization.rev)
