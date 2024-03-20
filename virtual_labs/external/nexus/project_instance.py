import asyncio

import httpx
from pydantic import UUID4

from virtual_labs.external.nexus.acl_list import project_admin_acls, project_member_acls
from virtual_labs.external.nexus.default_mapping import DEFAULT_MAPPING
from virtual_labs.external.nexus.defaults import (
    DEFAULT_API_MAPPING,
    DEFAULT_PROJECT_VOCAB,
    ES_RESOURCE_TYPE,
    ES_VIEW_ID,
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

        await nexus_interface.create_es_view(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            mapping=DEFAULT_MAPPING,
            view_id=ES_VIEW_ID,
            resource_types=ES_RESOURCE_TYPE,
            source_as_text=False,
            include_metadata=True,
            include_deprecated=False,
        )

        last_acl_rev = (
            (
                await nexus_interface.retrieve_project_latest_acls(
                    virtual_lab_id=virtual_lab_id, project_id=project_id
                )
            )
            .results[0]
            .rev
        )

        appended_admin_group_acls = await nexus_interface.append_project_acls(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            group_id=admin_group_id,
            permissions=project_admin_acls,
            rev=last_acl_rev,
        )

        await nexus_interface.append_project_acls(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            group_id=member_group_id,
            permissions=project_member_acls,
            rev=appended_admin_group_acls.rev,
        )

        nexus_tasks = [
            nexus_interface.create_nexus_es_aggregate_view(
                virtual_lab_id=virtual_lab_id, project_id=project_id
            ),
            nexus_interface.create_nexus_sp_aggregate_view(
                virtual_lab_id=virtual_lab_id, project_id=project_id
            ),
        ]

        await asyncio.gather(*list(map(asyncio.create_task, nexus_tasks)))

        return nexus_project.self
