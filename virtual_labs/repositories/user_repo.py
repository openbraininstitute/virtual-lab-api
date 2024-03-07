from typing import Any, Dict, List

from keycloak import KeycloakAdmin  # type: ignore
from pydantic import UUID4, EmailStr

from virtual_labs.infrastructure.kc.config import get_realm_pool


class UserRepository:
    Kc: KeycloakAdmin

    def __init__(self, realm: str) -> None:
        self.Kc = get_realm_pool(realm)

    def retrieve_user_from_kc(self, user_id: str) -> Any | Dict[str, str]:
        return self.Kc.get_user(user_id)

    def retrieve_user_groups(self, user_id: str) -> Any | Dict[str, str]:
        return self.Kc.get_user_groups(user_id=user_id)

    def retrieve_users_from_kc_batch(
        self, *, users: list[str]
    ) -> List[Any | Dict[str, str]]:
        users_list = []
        for u in users:
            users_list.append(self.retrieve_user_from_kc(u))

        return users_list

    def retrieve_users_per_project(self, project_id: UUID4) -> None:
        pass

    def detach_user_from_project(
        self, virtual_lab_id: UUID4, project_id: UUID4, user_email: EmailStr
    ) -> None:
        # need kc instance
        return

    def attach_user_to_project(
        self, virtual_lab_id: UUID4, project_id: UUID4, user_email: EmailStr
    ) -> None:
        # need kc instance
        return
