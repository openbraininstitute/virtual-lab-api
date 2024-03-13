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
                data={
                    "description": description,
                    "apiMapping": apiMapping,
                    "vocab": vocab,
                    "base": project_base,
                },
            )

            data = response.json()
            return NexusProject(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus project {ex}")
            raise NexusError(
                message="Error during creating nexus project",
                type=NexusErrorValue.CREATE_PROJECT_ERROR,
            )

    async def retrieve_project_acls(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
    ) -> NexusAclList:
        nexus_acl_url = (
            f"{settings.NEXUS_DELTA_URI}/acls/{str(virtual_lab_id)}/{str(project_id)}"
        )

        try:
            response = await self.httpx_clt.get(
                nexus_acl_url,
            )
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
                data={
                    "@type": "Append",
                    "acl": [
                        {
                            "permissions": permissions,
                            "identity": {
                                "realm": settings.KC_REALM_NAME,
                                "group": group_id,
                            },
                        },
                    ],
                },
            )
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
        rev: str,
    ) -> NexusAcls:
        nexus_acl_url = f"{settings.NEXUS_DELTA_URI}/acls/{str(virtual_lab_id)}/{str(project_id)}?rev={rev}"

        try:
            response = await self.httpx_clt.delete(
                nexus_acl_url,
            )
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
                data={"@type": AGGREGATE_ELASTIC_SEARCH_VIEW, "views": views},
            )
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
                data={"@type": AGGREGATE_SPARQL_VIEW, "views": views},
            )
            data = response.json()

            return NexusResource(**data)
        except Exception as ex:
            logger.error(f"Error during creating nexus sp aggregate view {ex}")
            raise NexusError(
                message="Error during creating nexus sp aggregate view",
                type=NexusErrorValue.CREATE_SP_AGG_VIEW_ERROR,
            )

    # async def create_nexus_resource(
    #     self, *, org_label: str, project_label: str, resource_id: str
    # ) -> NexusResource:
    #     nexus_resource_url = f"{settings.NEXUS_DELTA_URI}/resources/{org_label}/{project_label}/_/{resource_id}"
    #     try:
    #         response = await self.httpx_clt.get(nexus_resource_url)
    #         data = response.json()

    #         return NexusResource(**data)
    #     except Exception as ex:
    #         logger.error(f"Error during creating nexus resource {ex}")
    #         raise NexusError(
    #             "Error during creating nexus resource",
    #             type=NexusErrorValue.CREATE_RESOURCE,
    #         )

    # async def fetch_nexus_resource(
    #     self,
    #     *,
    #     org_label: str,
    #     project_label: str,
    #     resource_id: str,
    #     payload: Dict[str, Any],
    # ) -> NexusResource:
    #     nexus_resource_url = f"{settings.NEXUS_DELTA_URI}/resources/{org_label}/{project_label}/_/{resource_id}"
    #     try:
    #         response = await self.httpx_clt.post(nexus_resource_url, data=payload)
    #         data = response.json()

    #         return NexusResource(**data)
    #     except Exception as ex:
    #         logger.error(f"Error during fetching nexus resource {ex}")
    #         raise NexusError(
    #             "Error during fetching nexus resource",
    #             type=NexusErrorValue.FETCH_RESOURCE,
    #         )

    # async def create_nexus_resolver(
    #     self,
    #     *,
    #     org_label: str,
    #     project_label: str,
    #     projects: List[str],
    #     identities: List[NexusIdentity],
    #     priority: int = 50,
    # ) -> NexusResource:
    #     nexus_resolver_url = (
    #         f"{settings.NEXUS_DELTA_URI}/resolvers/{org_label}/{project_label}"
    #     )
    #     try:
    #         response = await self.httpx_clt.post(
    #             nexus_resolver_url,
    #             data={
    #                 "@type": ["CrossProject"],
    #                 "projects": projects,
    #                 "identities": identities,
    #                 "priority": priority,
    #             },
    #         )
    #         data = response.json()

    #         return NexusResource(**data)
    #     except Exception as ex:
    #         logger.error(f"Error during fetching nexus resolver {ex}")
    #         raise NexusError(
    #             "Error during creating nexus resolver",
    #             type=NexusErrorValue.CREATE_RESOLVER,
    #         )

    # async def create_nexus_es_view(
    #     self,
    #     *,
    #     org_label: str,
    #     project_label: str,
    #     payload: NexusElasticSearchViewMapping,
    #     source_as_text: Optional[bool] = False,
    #     include_metadata: bool = True,
    #     include_deprecated: bool = False,
    #     resource_types: Optional[Set[str]] = None,
    #     view_id: Optional[
    #         str
    #     ] = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    # ) -> NexusResource:
    #     nexus_es_view_url = (
    #         f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
    #     )
    #     try:
    #         updated_payload = payload.__dict__
    #         updated_payload.update(
    #             {
    #                 "includeMetadata": include_metadata,
    #                 "includeDeprecated": include_deprecated,
    #             }
    #         )
    #         if resource_types:
    #             updated_payload.update({"resourceTypes": resource_types})
    #         if source_as_text:
    #             updated_payload.update({"sourceAsText": source_as_text})

    #         response = await self.httpx_clt.put(nexus_es_view_url, data=updated_payload)

    #         data = response.json()

    #         return NexusResource(**data)
    #     except Exception as ex:
    #         logger.error(f"Error during creating nexus es view {ex}")
    #         raise NexusError(
    #             "Error during creating nexus es view",
    #             type=NexusErrorValue.CREATE_ES_VIEW,
    #         )

    # async def create_nexus_sp_view(
    #     self,
    #     *,
    #     org_label: str,
    #     project_label: str,
    #     include_metadata: bool = True,
    #     include_deprecated: bool = False,
    #     resource_schemas: Optional[Set[str]] = None,
    #     resource_types: Optional[Set[str]] = None,
    #     view_id: Optional[
    #         str
    #     ] = "https://bbp.epfl.ch/neurosciencegraph/data/views/es/dataset",
    # ) -> NexusResource:
    #     nexus_es_view_url = (
    #         f"{settings.NEXUS_DELTA_URI}/views/{org_label}/{project_label}/{view_id}"
    #     )
    #     try:
    #         updated_payload = {
    #             "includeMetadata": include_metadata,
    #             "includeDeprecated": include_deprecated,
    #             "@type": ["View", "SparqlView"],
    #         }
    #         if resource_types:
    #             updated_payload.update({"resourceTypes": resource_types})
    #         if resource_schemas:
    #             updated_payload.update({"resourceSchemas": resource_schemas})

    #         response = await self.httpx_clt.put(nexus_es_view_url, data=updated_payload)

    #         data = response.json()

    #         return NexusResource(**data)
    #     except Exception as ex:
    #         logger.error(f"Error during creating nexus es view {ex}")
    #         raise NexusError(
    #             "Error during creating nexus es view",
    #             type=NexusErrorValue.CREATE_ES_VIEW,
    #         )
