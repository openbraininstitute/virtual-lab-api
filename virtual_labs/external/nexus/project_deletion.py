import httpx
from pydantic import UUID4

from virtual_labs.external.nexus.project_interface import NexusProjectInterface


async def delete_nexus_project(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
) -> bool:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport) as httpx_clt:
        nexus_interface = NexusProjectInterface(httpx_clt)
        revision = (
            await nexus_interface.retrieve_project(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
            )
        ).rev
        deleted_project = await nexus_interface.deprecate_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            revision=revision,
        )

        return deleted_project.deprecated
