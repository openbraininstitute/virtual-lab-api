import asyncio

import httpx
from pydantic import UUID4

from virtual_labs.external.nexus.acl_list import project_admin_acls, project_member_acls
from virtual_labs.external.nexus.defaults import (
    DEFAULT_API_MAPPING,
    DEFAULT_PROJECT_VOCAB,
)
from virtual_labs.external.nexus.project_interface import NexusProjectInterface


async def instantiate_nexus_project(
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    description: str | None,
    admin_group_id: str,
    member_group_id: str,
) -> str:
    transport = httpx.AsyncHTTPTransport(retries=3)

    async with httpx.AsyncClient(transport=transport) as httpx_clt:
        nexus_interface = NexusProjectInterface(httpx_clt)
        nexus_project = await nexus_interface.create_nexus_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            vocab=DEFAULT_PROJECT_VOCAB,
            apiMapping=DEFAULT_API_MAPPING,
            description=description,
        )
        # create new acls for the project for the two groups
        nexus_tasks = [
            nexus_interface.append_project_acls(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                group_id=admin_group_id,
                permissions=project_admin_acls,
            ),
            nexus_interface.append_project_acls(
                virtual_lab_id=virtual_lab_id,
                project_id=project_id,
                group_id=member_group_id,
                permissions=project_member_acls,
            ),
            nexus_interface.create_nexus_es_aggregate_view(
                virtual_lab_id=virtual_lab_id, project_id=project_id
            ),
            nexus_interface.create_nexus_sp_aggregate_view(
                virtual_lab_id=virtual_lab_id, project_id=project_id
            ),
        ]

        await asyncio.gather(*list(map(asyncio.create_task, nexus_tasks)))

        return nexus_project._self
