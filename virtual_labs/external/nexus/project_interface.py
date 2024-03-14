from typing import Any, Dict, List, Optional

from httpx import AsyncClient
from loguru import logger
from pydantic import UUID4

from virtual_labs.core.exceptions.nexus_error import NexusError, NexusErrorValue
from virtual_labs.external.nexus.defaults import (
    AGGREGATE_ELASTIC_SEARCH_VIEW,
    AGGREGATE_SPARQL_VIEW,
    ES_VIEW_ID,
    ES_VIEWS,
    SP_VIEW_ID,
    SP_VIEWS,
    prep_project_base,
)
from virtual_labs.external.nexus.models import (
    NexusAclList,
    NexusAcls,
    NexusApiMapping,
    NexusProject,
    NexusResource,
)
from virtual_labs.infrastructure.settings import settings


def create_context(vocab: str) -> Dict[str, Any]:
    return {
        "@context": ["https://neuroshapes.org", {"@vocab": vocab}],
        "@id": "https://bbp.neuroshapes.org",
    }


class NexusProjectInterface:
    httpx_clt: AsyncClient

    def __init__(self, httpx_clt: AsyncClient) -> None:
        self.httpx_clt = httpx_clt
        pass

    async def create_nexus_project(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        description: Optional[str],
        apiMapping: List[NexusApiMapping],
        vocab: str,
    ) -> NexusProject:
        nexus_project_url = (
            f"{settings.NEXUS_DELTA_URI}/projects/{virtual_lab_id}/{project_id}"
        )
        project_base = prep_project_base(
            virtual_lab_id=str(virtual_lab_id), project_id=str(project_id)
        )
        try:
            response = await self.httpx_clt.put(
                nexus_project_url,
                json={
                    "description": description,
                    "apiMappings": apiMapping,
                    "vocab": vocab,
                    "base": project_base,
                },
            )
            response.raise_for_status()

            data = response.json()
            return NexusProject(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus project {ex}")
            raise NexusError(
                message="Error during creating nexus project",
                type=NexusErrorValue.CREATE_PROJECT_ERROR,
            )

    async def retrieve_project_latest_acls(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
    ) -> NexusAclList:
        nexus_acl_url = f"{settings.NEXUS_DELTA_URI}/acls/{str(virtual_lab_id)}/{str(project_id)}?ancestors=true"
        try:
            response = await self.httpx_clt.get(nexus_acl_url)
            response.raise_for_status()

            data = response.json()
            return NexusAclList(**data)
        except Exception as ex:
            logger.error(f"Error during fetching nexus project acls {ex}")
            raise NexusError(
                message="Error during fetching nexus project acls",
                type=NexusErrorValue.FETCH_PROJECT_ACL_ERROR,
            )

    async def append_project_acls(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        group_id: str,
        permissions: List[str] | None = None,
    ) -> NexusAcls:
        nexus_acl_url = (
            f"{settings.NEXUS_DELTA_URI}/acls/{str(virtual_lab_id)}/{str(project_id)}"
        )

        try:
            response = await self.httpx_clt.patch(
                nexus_acl_url,
                json={
                    "@type": "Append",
                    "acl": [
                        {
                            "permissions": permissions,
                            "identity": {
                                "realm": settings.KC_REALM_NAME,
                                "group": str(group_id),
                            },
                        },
                    ],
                },
            )
            response.raise_for_status()

            data = response.json()
            return NexusAcls(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus project acls {ex}")
            raise NexusError(
                message="Error during creating nexus project acls",
                type=NexusErrorValue.CREATE_PROJECT_ACL_ERROR,
            )

    async def delete_project_acl_revision(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
    ) -> NexusAcls:
        nexus_acl_url = (
            f"{settings.NEXUS_DELTA_URI}/acls/{str(virtual_lab_id)}/{str(project_id)}"
        )

        try:
            response = await self.httpx_clt.delete(nexus_acl_url)
            response.raise_for_status()

            data = response.json()
            return NexusAcls(**data)
        except Exception as ex:
            logger.error(f"Error during deleting nexus acl list {ex}")
            raise NexusError(
                message="Error during deleting nexus project acl list",
                type=NexusErrorValue.DELETE_PROJECT_ACL_ERROR,
            )

    async def deprecate_project(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
    ) -> NexusProject:
        nexus_acl_url = f"{settings.NEXUS_DELTA_URI}/projects/{str(virtual_lab_id)}/{str(project_id)}"

        try:
            response = await self.httpx_clt.delete(
                nexus_acl_url,
            )
            response.raise_for_status()

            data = response.json()
            return NexusProject(**data)
        except Exception as ex:
            logger.error(f"Error during deprecation of nexus project {ex}")
            raise NexusError(
                message="Error during deprecation of nexus project",
                type=NexusErrorValue.DEPRECATE_PROJECT_ERROR,
            )

    async def create_nexus_es_aggregate_view(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        view_id: str = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = f"{settings.NEXUS_DELTA_URI}/views/{str(virtual_lab_id)}/{str(project_id)}/{view_id}"
        views = [
            {
                "project": f"{str(virtual_lab_id)}/{str(project_id)}",
                "viewId": ES_VIEW_ID,
            }
        ] + ES_VIEWS

        try:
            response = await self.httpx_clt.put(
                nexus_es_view_url,
                json={"@type": AGGREGATE_ELASTIC_SEARCH_VIEW, "views": views},
            )
            response.raise_for_status()

            data = response.json()
            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus es aggregate view {ex}")
            raise NexusError(
                message="Error during creating nexus es aggregate view",
                type=NexusErrorValue.CREATE_ES_AGG_VIEW_ERROR,
            )

    async def create_nexus_sp_aggregate_view(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        view_id: str = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = f"{settings.NEXUS_DELTA_URI}/views/{str(virtual_lab_id)}/{str(project_id)}/{view_id}"
        views = [
            {"project": f"{virtual_lab_id}/{project_id}", "viewId": SP_VIEW_ID}
        ] + SP_VIEWS

        try:
            response = await self.httpx_clt.put(
                nexus_es_view_url,
                json={"@type": AGGREGATE_SPARQL_VIEW, "views": views},
            )
            response.raise_for_status()

            data = response.json()
            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus sp aggregate view {ex}")
            raise NexusError(
                message="Error during creating nexus sp aggregate view",
                type=NexusErrorValue.CREATE_SP_AGG_VIEW_ERROR,
            )
