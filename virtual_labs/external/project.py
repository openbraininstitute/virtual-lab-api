from datetime import datetime
from typing import Annotated, List

from httpx import AsyncClient
from loguru import logger
from pydantic import UUID4, AnyUrl, BaseModel, Field

from virtual_labs.infrastructure.settings import settings


class NexusBase(BaseModel):
    context: Annotated[List[AnyUrl], Field(alias="@context")] = []
    id: Annotated[AnyUrl | str, Field(alias="@id")] = ""
    type: Annotated[str | List[str], Field(alias="@type")] = ""
    _createdAt: datetime | None = None
    _createdBy: datetime | None = None
    _deprecated: bool | None = None
    _self: AnyUrl | None = None


class NexusProject(NexusBase):
    _label: str | None = None
    _uuid: UUID4 | None = None


class NexusAcls(NexusBase):
    type: Annotated[str | List[str], Field(alias="@type")] = "AccessControlList"


async def create_nexus_project(
    httpx_clt: AsyncClient, virtual_lab_id: UUID4, project_id: UUID4, description: str
) -> NexusProject | None:
    nexus_project_url = (
        f"{settings.NEXUS_DELTA_URI}/projects/{virtual_lab_id}/{project_id}"
    )
    try:
        response = await httpx_clt.put(
            nexus_project_url, data={"description": description}
        )

        data = response.json()
        return NexusProject(**data)
    except Exception as ex:
        logger.error(f"Error during creating nexus project {ex}")
        return None


async def create_project_permissions(
    httpx_clt: AsyncClient,
    virtual_lab_id: UUID4,
    project_id: UUID4,
    group_id: str,
) -> NexusAcls | None:
    nexus_acl_url = f"{settings.NEXUS_DELTA_URI}/acls/{virtual_lab_id}/{project_id}"

    try:
        response = await httpx_clt.put(
            nexus_acl_url,
            data={
                "acl": [
                    {
                        # TODO: get permission from core/permissions depends on the entity/role
                        "permissions": ["projects/read", "projects/write"],
                        "identity": {
                            "realm": settings.KC_REALM_NAME,
                            "group": group_id,
                        },
                    },
                ]
            },
        )
        data = response.json()
        return NexusAcls(**data)
    except Exception as ex:
        logger.error(f"Error during creating nexus project {ex}")
        return None
