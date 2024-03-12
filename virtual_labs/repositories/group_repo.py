from typing import Any, Dict, List

from keycloak import KeycloakAdmin  # type: ignore
from pydantic import UUID4

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.project import ProjectCreationModel
from virtual_labs.infrastructure.kc.config import kc_realm_admin


class GroupQueryRepository:
    Kc: KeycloakAdmin

    def __init__(self) -> None:
        self.Kc = kc_realm_admin

    # TODO: the return type should be update, probably Keycloack will return UserRepresentation
    def retrieve_group_users(self, group_id: str) -> Any | Dict[str, str] | List[str]:
        return self.Kc.get_group_members(group_id=group_id)


class GroupMutationRepository:
    Kc: KeycloakAdmin

    def __init__(self) -> None:
        self.Kc = kc_realm_admin

    def create_virtual_lab_group(
        self,
        *,
        virtual_lab_id: UUID4,
        vl_name: str,
        role: UserRoleEnum,
    ) -> str | None | Any:
        """
        NOTE: you can not set the ID even in the docs says that is Optional
        virtual lab group must be following this format
        vl/vl-app-id/role
        """
        return self.Kc.create_group(
            {
                "name": "vl/{}/{}".format(virtual_lab_id, role.value),
                "attributes": {
                    "_name": [vl_name],
                },
            }
        )

    def create_project_group(
        self,
        *,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        role: UserRoleEnum,
        payload: ProjectCreationModel,
    ) -> str | None | Any:
        """
        NOTE: you can not set the ID even in the docs says that is Optional
        project group must be following this format
        project/virtual_lab_id/project_id/role
        """
        return self.Kc.create_group(
            {
                # TODO: if we will use flat structure then this one must be removed
                # "parentId": f"vl/{virtual_lab_id}",
                "name": "project/{}/{}/{}".format(
                    virtual_lab_id, project_id, role.value
                ),
                "attributes": {
                    "_name": [payload.name],
                    "_description": [payload.description],
                },
            },
            # TODO: if we will use flat structure then this one must be removed
            # parent=f"vl/{virtual_lab_id}",
        )

    def delete_group(self, *, group_id: str) -> Any | Dict[str, str]:
        return self.Kc.delete_group(group_id=group_id)
