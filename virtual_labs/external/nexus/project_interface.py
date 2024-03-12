from typing import Any, Dict, List, Optional, Set

from httpx import AsyncClient
from loguru import logger
from pydantic import UUID4, AnyUrl

from virtual_labs.core.exceptions.nexus_error import NexusError, NexusErrorValue
from virtual_labs.external.nexus.defaults import (
    AGGREGATE_ELASTIC_SEARCH_VIEW,
    AGGREGATE_SPARQL_VIEW,
    ES_VIEW_ID,
    ES_VIEWS,
    SP_VIEW_ID,
    SP_VIEWS,
)
from virtual_labs.external.nexus.models import (
    NexusAcls,
    NexusApiMapping,
    NexusElasticSearchViewMapping,
    NexusIdentity,
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
        description: str,
        apiMapping: List[NexusApiMapping],
        base: AnyUrl,
        vocab: str,
    ) -> NexusProject:
        nexus_project_url = (
            f"{settings.NEXUS_DELTA_URI}/projects/{virtual_lab_id}/{project_id}"
        )
        try:
            response = await self.httpx_clt.put(
                nexus_project_url,
                data={
                    "description": description,
                    "apiMapping": apiMapping,
                    "base": base,
                    "vocab": vocab,
                },
            )

            data = response.json()
            return NexusProject(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus project {ex}")
            raise NexusError(
                "Error during creating nexus project",
                type=NexusErrorValue.CREATE_PROJECT,
            )

    async def create_project_permissions(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        group_id: str,
    ) -> NexusAcls:
        nexus_acl_url = f"{settings.NEXUS_DELTA_URI}/acls/{virtual_lab_id}/{project_id}"

        try:
            response = await self.httpx_clt.put(
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
            logger.error(f"Error during creating nexus project permissions {ex}")
            raise NexusError(
                "Error during creating nexus project permissions",
                type=NexusErrorValue.CREATE_PROJECT_PERMISSION,
            )

    async def create_nexus_resource(
        self, *, org_label: str, project_label: str, resource_id: str
    ) -> NexusResource:
        nexus_resource_url = f"{settings.NEXUS_DELTA_URI}/resources/{org_label}/{project_label}/_/{resource_id}"
        try:
            response = await self.httpx_clt.get(nexus_resource_url)
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus resource {ex}")
            raise NexusError(
                "Error during creating nexus resource",
                type=NexusErrorValue.CREATE_RESOURCE,
            )

    async def fetch_nexus_resource(
        self,
        *,
        org_label: str,
        project_label: str,
        resource_id: str,
        payload: Dict[str, Any],
    ) -> NexusResource:
        nexus_resource_url = f"{settings.NEXUS_DELTA_URI}/resources/{org_label}/{project_label}/_/{resource_id}"
        try:
            response = await self.httpx_clt.post(nexus_resource_url, data=payload)
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during fetching nexus resource {ex}")
            raise NexusError(
                "Error during fetching nexus resource",
                type=NexusErrorValue.FETCH_RESOURCE,
            )

    async def create_nexus_resolver(
        self,
        *,
        org_label: str,
        project_label: str,
        projects: List[str],
        identities: List[NexusIdentity],
        priority: int = 50,
    ) -> NexusResource:
        nexus_resolver_url = (
            f"{settings.NEXUS_DELTA_URI}/resolvers/{org_label}/{project_label}"
        )
        try:
            response = await self.httpx_clt.post(
                nexus_resolver_url,
                data={
                    "@type": ["CrossProject"],
                    "projects": projects,
                    "identities": identities,
                    "priority": priority,
                },
            )
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during fetching nexus resolver {ex}")
            raise NexusError(
                "Error during creating nexus resolver",
                type=NexusErrorValue.CREATE_RESOLVER,
            )

    async def create_nexus_es_view(
        self,
        *,
        org_label: str,
        project_label: str,
        payload: NexusElasticSearchViewMapping,
        source_as_text: Optional[bool] = False,
        include_metadata: bool = True,
        include_deprecated: bool = False,
        resource_types: Optional[Set[str]] = None,
        view_id: Optional[
            str
        ] = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = (
            f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
        )
        try:
            updated_payload = payload.__dict__
            updated_payload.update(
                {
                    "includeMetadata": include_metadata,
                    "includeDeprecated": include_deprecated,
                }
            )
            if resource_types:
                updated_payload.update({"resourceTypes": resource_types})
            if source_as_text:
                updated_payload.update({"sourceAsText": source_as_text})

            response = await self.httpx_clt.put(nexus_es_view_url, data=updated_payload)

            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus es view {ex}")
            raise NexusError(
                "Error during creating nexus es view",
                type=NexusErrorValue.CREATE_ES_VIEW,
            )

    async def create_nexus_sp_view(
        self,
        *,
        org_label: str,
        project_label: str,
        include_metadata: bool = True,
        include_deprecated: bool = False,
        resource_schemas: Optional[Set[str]] = None,
        resource_types: Optional[Set[str]] = None,
        view_id: Optional[
            str
        ] = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = (
            f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
        )
        try:
            updated_payload = {
                "includeMetadata": include_metadata,
                "includeDeprecated": include_deprecated,
                "@type": ["View", "SparqlView"],
            }
            if resource_types:
                updated_payload.update({"resourceTypes": resource_types})
            if resource_schemas:
                updated_payload.update({"resourceSchemas": resource_schemas})

            response = await self.httpx_clt.put(nexus_es_view_url, data=updated_payload)

            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus es view {ex}")
            raise NexusError(
                "Error during creating nexus es view",
                type=NexusErrorValue.CREATE_SP_VIEW,
            )

    async def create_nexus_es_aggregate_view(
        self,
        *,
        org_label: str,
        project_label: str,
        view_id: str = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = (
            f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
        )
        views = [
            {"project": f"{org_label}/{project_label}", "viewId": ES_VIEW_ID}
        ] + ES_VIEWS

        try:
            response = await self.httpx_clt.put(
                nexus_es_view_url,
                data={"@type": AGGREGATE_ELASTIC_SEARCH_VIEW, "views": views},
            )
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus es aggregate view {ex}")
            raise NexusError(
                "Error during creating nexus es aggregate view",
                type=NexusErrorValue.CREATE_ES_AGG_VIEW,
            )

    async def create_nexus_sp_aggregate_view(
        self,
        *,
        org_label: str,
        project_label: str,
        view_id: str = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    ) -> NexusResource:
        nexus_es_view_url = (
            f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
        )
        views = [
            {"project": f"{org_label}/{project_label}", "viewId": SP_VIEW_ID}
        ] + SP_VIEWS

        try:
            response = await self.httpx_clt.put(
                nexus_es_view_url,
                data={"@type": AGGREGATE_SPARQL_VIEW, "views": views},
            )
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus sp aggregate view {ex}")
            raise NexusError(
                "Error during creating nexus sp aggregate view",
                type=NexusErrorValue.CREATE_SP_AGG_VIEW,
            )
