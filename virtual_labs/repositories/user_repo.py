from typing import Any, Dict, List, Literal, Tuple, cast
from uuid import UUID, uuid4

from keycloak import KeycloakAdmin  # type: ignore
from loguru import logger
from pydantic import UUID4

from virtual_labs.core.exceptions.identity_error import IdentityError
from virtual_labs.infrastructure.kc.config import kc_auth, kc_realm
from virtual_labs.infrastructure.kc.models import (
    GroupRepresentation,
    UserInfo,
    UserRepresentation,
)


class UserQueryRepository:
    Kc: KeycloakAdmin

    def __init__(self) -> None:
        self.Kc = kc_realm
        self.Kc_auth = kc_auth

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        user = await self.Kc.a_get_user(user_id=user_id)
        return cast(Dict[str, Any], user)

    def retrieve_user_from_kc(self, user_id: str) -> UserRepresentation:
        try:
            return UserRepresentation(**self.Kc.get_user(user_id))
        except Exception as error:
            raise IdentityError(
                message=f"User with id {user_id} not found", detail=str(error)
            )

    def retrieve_user_by_email_soft(
        self, email: str
    ) -> List[UserRepresentation] | None:
        return [
            UserRepresentation(**user) for user in self.Kc.get_users({"email": email})
        ]

    def retrieve_user_by_email(self, email: str) -> UserRepresentation | None:
        users = self.Kc.get_users({"email": email})
        if not isinstance(users, list):
            logger.error(
                f"Expected a list of users for email {email} but received type {type(users)} : {users}"
            )
            raise ValueError(
                f"Expected a list of users for email {email} but received type {type(users)}"
            )

        match len(users):
            case 0:
                logger.debug(f"No user with email {email} found in keycloak")
                return None
            case 1:
                try:
                    return UserRepresentation(**users[0])
                except Exception:
                    logger.error(
                        f"Could not convert user from keycloak to UserRepresentation. Received value {users[0]}"
                    )
                    raise ValueError(
                        f"Received invalid user object for user with email {email}. {users[0]}"
                    )
            case _:
                # TODO: Should we expose this error to the client or do something else in this case
                logger.error(f"Found {len(users)} users with email {email} : {users}")
                raise ValueError(
                    f"Expected 1 user with email {email} but found {len(users)}"
                )

    def retrieve_user_groups(self, user_id: UUID4) -> List[GroupRepresentation]:
        try:
            groups = [
                GroupRepresentation(**group)
                for group in self.Kc.get_user_groups(user_id=user_id)
            ]
            return groups
        except Exception as error:
            logger.error(f"Error when retrieving groups for user {user_id}: {error}")
            raise IdentityError(
                message=f"Permissions for user {user_id} could not be retrieved.",
                detail=str(error),
            )

    def is_user_in_group(self, user_id: UUID4, group_id: str) -> bool:
        current_groups = [group.id for group in self.retrieve_user_groups(user_id)]
        return group_id in current_groups

    def get_all_users_count(self) -> int:
        return len(self.Kc.get_users())

    async def get_group_user_count(self, group_id: str) -> int:
        members = await self.Kc.a_get_group_members(group_id=group_id)
        return len(members)

    async def get_user_info(self, token: str) -> UserInfo:
        return cast(UserInfo, await self.Kc_auth.a_userinfo(token=token))


class UserMutationRepository:
    Kc: KeycloakAdmin

    def __init__(self) -> None:
        self.Kc = kc_realm
        self.Kc_auth = kc_auth

    def attach_user_to_group(
        self,
        *,
        user_id: UUID4,
        group_id: str,
    ) -> Any | Dict[str, str]:
        try:
            return self.Kc.group_user_add(user_id=user_id, group_id=group_id)
        except Exception as error:
            logger.error(
                f"Keycloak error when adding user {user_id} to group {group_id}: {error}"
            )
            err = IdentityError(
                message=f"Could not add user {user_id} to group {group_id}",
                detail=str(error),
            )
            err.add_note("Most likely the user does not exist in keycloak")
            raise err

    async def a_attach_user_to_group(
        self,
        *,
        user_id: UUID4,
        group_id: str,
    ) -> Any | Dict[str, str]:
        try:
            return await self.Kc.a_group_user_add(user_id=user_id, group_id=group_id)
        except Exception as error:
            logger.error(
                f"Keycloak error when adding user {user_id} to group {group_id}: {error}"
            )
            err = IdentityError(
                message=f"Could not add user {user_id} to group {group_id}",
                detail=str(error),
            )
            err.add_note("Most likely the user does not exist in keycloak")
            raise err

    def detach_user_from_group(
        self,
        *,
        user_id: UUID4,
        group_id: str,
    ) -> Any | Dict[str, str]:
        return self.Kc.group_user_remove(user_id=user_id, group_id=group_id)

    async def a_detach_user_from_group(
        self,
        *,
        user_id: UUID4,
        group_id: str,
    ) -> Any | Dict[str, str]:
        return await self.Kc.a_group_user_remove(user_id=user_id, group_id=group_id)

    def create_user(
        self,
        *,
        user_email: str,
    ) -> UUID4:
        # TODO: change the format later, this must be unique for keycloak
        username = user_email.split("@")[0] + "@" + uuid4().hex
        user_id = self.Kc.create_user(
            payload={"email": user_email, "username": username}
        )
        return UUID(user_id)

    def create_test_user(
        self,
        *,
        user_email: str,
    ) -> UUID4:
        # TODO: change the format later, this must be unique for keycloak
        username = user_email.split("@")[0] + "@" + uuid4().hex
        user_id = self.Kc.create_user(
            payload={
                "email": user_email,
                "username": username,
                "emailVerified": True,
                "enabled": True,
                "requiredActions": [],
            }
        )
        return cast(UUID4, user_id)

    async def update_user_custom_property(
        self,
        user_id: UUID,
        field: str,
        value: str,
        type: Literal["multiple", "unique"] = "unique",
    ) -> None:
        user = await self.Kc.a_get_user(user_id=user_id)

        update_data: Dict[str, Any] = {}
        update_data["email"] = user.get("email")
        update_data["firstName"] = user.get("firstName")
        update_data["lastName"] = user.get("lastName")
        attributes = user.get("attributes", {})

        property_field = {field: [value] if type == "multiple" else value}
        merged_attributes = {
            k: v if isinstance(v, list) else [str(v)] for k, v in attributes.items()
        }
        merged_attributes.update(cast(Dict[Any, List[Any]], property_field))
        update_data["attributes"] = merged_attributes

        await self.Kc.a_update_user(user_id=user_id, payload=update_data)

    async def update_user_custom_properties(
        self,
        user_id: UUID,
        properties: List[Tuple[str, str, Literal["multiple", "unique"]]],
    ) -> None:
        """
        update multiple custom properties for a user at once.

        Args:
            user_id: The UUID of the user to update
            properties: A list of tuples containing (field, value, type)
                        where type is either "multiple" or "unique"

        """
        user = await self.Kc.a_get_user(user_id=user_id)

        update_data: Dict[str, Any] = {}
        update_data["email"] = user.get("email")
        update_data["firstName"] = user.get("firstName")
        update_data["lastName"] = user.get("lastName")
        attributes = user.get("attributes", {})

        merged_attributes = {
            k: v if isinstance(v, list) else [str(v)] for k, v in attributes.items()
        }

        for field, value, prop_type in properties:
            property_field = {field: [value] if prop_type == "multiple" else value}
            merged_attributes.update(cast(Dict[Any, List[Any]], property_field))

        update_data["attributes"] = merged_attributes

        await self.Kc.a_update_user(user_id=user_id, payload=update_data)
