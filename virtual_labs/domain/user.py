from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, List, Optional, TypedDict

from pydantic import (
    UUID4,
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from virtual_labs.core.types import UserGroup, UserRoleEnum
from virtual_labs.infrastructure.db.models import SpeciesSelectionMode

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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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


class WorkspaceHierarchySpeciesPreference(BaseModel):
    """
    Request/Response model for brain region preference.
    Stores user's selected hierarchy, species taxonomy, and brain region context.
    """

    hierarchy_id: Optional[UUID4] = Field(
        default=None,
        description="UUID identifier for the selected hierarchy",
    )
    species_name: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Identifier for the species taxonomy",
    )
    brain_region_id: Optional[UUID4] = Field(
        default=None,
        description="UUID identifier for the selected brain region",
    )
    brain_region_name: Optional[str] = Field(
        default=None,
        description="Annotation value for the brain region",
    )

    species_selection_mode: SpeciesSelectionMode = "focused"

    @model_validator(mode="after")
    def _check(self) -> "WorkspaceHierarchySpeciesPreference":
        if self.species_selection_mode == "all":
            # coerce all id/name fields to None when mode is 'all'
            self.hierarchy_id = None
            self.species_name = None
            self.brain_region_id = None
            self.brain_region_name = None
        else:
            # focused mode must carry a hierarchy + species (matches current contract)
            if not self.hierarchy_id or not self.species_name:
                raise ValueError(
                    "hierarchy_id and species_name are required in 'focused' mode"
                )
        return self


class WorkspaceHierarchySpeciesPreferenceDict(TypedDict):
    """TypedDict for workspace hierarchy species preference stored in DB JSON"""

    hierarchy_id: Optional[str]  # UUID stored as string in JSON
    species_name: Optional[str]
    brain_region_id: Optional[str]  # UUID stored as string in JSON
    brain_region_name: Optional[str]
    species_selection_mode: (
        SpeciesSelectionMode  # absent == "focused" for backward-compat
    )


class WorkspaceHierarchySpeciesPreferenceResponse(BaseModel):
    """Response model for workspace hierarchy species preference"""

    user_id: UUID4
    preference: Optional[WorkspaceHierarchySpeciesPreference] = None
    updated_at: Optional[datetime] = None


class UserRecord(BaseModel):
    user_id: UUID4
    hierarchy_preference: Optional[WorkspaceHierarchySpeciesPreference] = None
    recent_workspace: Optional[Workspace] = None
    email: EmailStr
    email_verified: bool
