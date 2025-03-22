from datetime import datetime
from typing import Annotated, Any, List, Optional

from pydantic import (
    UUID4,
    AliasChoices,
    BaseModel,
    EmailStr,
    Field,
    computed_field,
    field_validator,
)

from virtual_labs.core.types import UserGroup, UserRoleEnum


class ShortenedUser(BaseModel):
    id: UUID4 | None
    username: str
    email: EmailStr
    createdTimestamp: Annotated[datetime, Field(alias="created_at", default="")]
    first_name: Annotated[
        str, Field(validation_alias=AliasChoices("firstName"), default="")
    ]
    last_name: Annotated[
        str, Field(validation_alias=AliasChoices("lastName"), default="")
    ]

    @field_validator("createdTimestamp", mode="before")
    @classmethod
    def convert_timestamp(cls, v: int) -> Any:
        if isinstance(v, int):
            return datetime.fromtimestamp(v / 1000)
        return v

    @computed_field  # type: ignore
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    class Config:
        from_attributes = True
        # populate_by_name = True


class AllUsersCount(BaseModel):
    total: int = Field(
        description="Count of all users in BBP keycloak (including the ones that may not have not explicitly signed into OBP or have any virtual labs)"
    )


class UserWithInviteStatus(ShortenedUser):
    invite_accepted: bool
    role: UserRoleEnum


class UserAgentResponse(BaseModel):
    id: str
    given_name: str
    family_name: str
    name: str
    createdAt: datetime
    type: list[str]


class Address(BaseModel):
    """User address information"""

    street: Optional[str] = None
    postal_code: Optional[str] = None
    locality: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


class UserProfile(BaseModel):
    """User profile information"""

    id: UUID4
    preferred_username: str
    email: EmailStr
    first_name: str
    last_name: str
    email_verified: bool
    address: Optional[Address] = None

    @computed_field  # type: ignore
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    class Config:
        from_attributes = True


class UpdateUserProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address: Optional[Address] = None


class UserProfileResponse(BaseModel):
    profile: UserProfile


class UserGroupsResponse(BaseModel):
    groups: List[UserGroup]
