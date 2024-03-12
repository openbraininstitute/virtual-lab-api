from httpx import AsyncClient
from pydantic import UUID4

from virtual_labs.core.exceptions.nexus_error import NexusError, NexusErrorValue
from virtual_labs.core.permissions import project_admin_acls, project_member_acls
from virtual_labs.external.nexus.defaults import (
    DEFAULT_API_MAPPING,
    DEFAULT_PROJECT_VOCAB,
)
from virtual_labs.external.nexus.project_interface import NexusProjectInterface


# TODO: use asyncio to gather both requests
async def instantiate_nexus_project(
    httpx_clt: AsyncClient,
    *,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    description: str | None,
    admin_group_id: str,
    member_group_id: str,
) -> str:
    nexus_interface = NexusProjectInterface(httpx_clt)

    try:
        nexus_project = await nexus_interface.create_nexus_project(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            vocab=DEFAULT_PROJECT_VOCAB,
            apiMapping=DEFAULT_API_MAPPING,
            description=description,
        )
        # TODO: gather this two in asyncio
        await nexus_interface.create_project_acls(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            group_id=admin_group_id,
            permissions=project_admin_acls,
        )
        await nexus_interface.create_project_acls(
            virtual_lab_id=virtual_lab_id,
            project_id=project_id,
            group_id=member_group_id,
            permissions=project_member_acls,
        )
        # TODO: create aggregate views (both ES/SP)
        assert isinstance(nexus_project._self, str)

        return nexus_project._self
    except NexusError as ex:
        raise ex
    except AssertionError:
        raise NexusError(type=NexusErrorValue.GENERIC)
