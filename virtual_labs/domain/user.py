from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, List, Optional, TypedDict

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

if TYPE_CHECKING:
    from virtual_labs.domain.labs import VirtualLabDetails
    from virtual_labs.domain.project import ProjectVlOut


class ShortenedUser(BaseModel):
    id: UUID4 | None
    username: str
    email: EmailStr
    createdTimestamp: Annotated[datetime, Field(alias="created_at", default="")]
    first_name: Annotated[
        Optional[str], Field(validation_alias=AliasChoices("firstName"), default="")
    ]
    last_name: Annotated[
        Optional[str], Field(validation_alias=AliasChoices("lastName"), default="")
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
        return (f"{self.first_name} {self.last_name}").strip()

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
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address: Optional[Address] = None


class UserProfileResponse(BaseModel):
    profile: UserProfile


class UserGroupsResponse(BaseModel):
    groups: List[UserGroup]


# Recent Workspace Domain Models
class Workspace(BaseModel):
    """Represents a workspace consisting of a virtual lab and project combination"""

    virtual_lab_id: UUID4
    project_id: UUID4


class RecentWorkspaceOut(BaseModel):
    """Response model for recent workspace information"""

    user_id: UUID4
    workspace: Optional[Workspace] = None
    updated_at: Optional[datetime] = None


class SetRecentWorkspaceRequest(BaseModel):
    """Request model for setting recent workspace"""

    workspace: Workspace


class RecentWorkspaceResponse(BaseModel):
    """API response wrapper for recent workspace"""

    recent_workspace: RecentWorkspaceOut


class RecentWorkspaceOutWithDetails(RecentWorkspaceOut):
    """Response model for recent workspace with full details"""

    virtual_lab: Optional["VirtualLabDetails"] = None
    project: Optional["ProjectVlOut"] = None


class RecentWorkspaceResponseWithDetails(BaseModel):
    """API response wrapper for recent workspace with details"""

    recent_workspace: RecentWorkspaceOutWithDetails


class OnboardingFeature(str, Enum):
    """Enum for supported onboarding features"""

    WORKSPACE_DATA = "workspace-data"
    WORKSPACE_PROJECT = "workspace-project"
    WORKSPACE_WORKFLOW = "workspace-workflow"


class OnboardingStatus(BaseModel):
    """Model representing the onboarding status for a specific feature"""

    completed: bool
    completed_at: Optional[datetime] = None
    current_step: Optional[int] = None
    dismissed: bool = False


class OnboardingUpdateRequest(BaseModel):
    """Request model for updating onboarding status"""

    completed: Optional[bool] = None
    current_step: Optional[int] = None
    dismissed: Optional[bool] = None


class OnboardingStatusDict(TypedDict):
    """TypedDict for onboarding status stored in DB JSON"""

    completed: bool
    completed_at: Optional[str]
    current_step: Optional[int]
    dismissed: bool
