from datetime import datetime
from typing import Annotated, List

from httpx import AsyncClient
from loguru import logger
from pydantic import UUID4, AnyUrl, BaseModel, Field

from virtual_labs.infrastructure.settings import settings


class NexusProject(BaseModel):
    context: Annotated[List[AnyUrl], Field(alias="@context")] = []
    id: Annotated[AnyUrl | str, Field(alias="@id")] = ""
    type: Annotated[str | List[str], Field(alias="@type")] = ""
    _createdAt: datetime | None = None
    _createdBy: datetime | None = None
    _deprecated: bool | None = None
    _label: str | None = None
    _uuid: UUID4 | None = None
    _self: AnyUrl | None = None


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
