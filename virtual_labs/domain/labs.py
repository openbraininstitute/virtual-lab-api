from datetime import datetime
from enum import Enum, StrEnum, auto
from typing import Generic, TypeVar

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field

from virtual_labs.domain.user import ShortenedUser, UserWithInviteStatus

T = TypeVar("T")


class ComputeCell(str, Enum):
    """Enum representing available compute cells."""

    CELL_A = "cell_a"
    CELL_B = "cell_b"


class LabResponse(BaseModel, Generic[T]):
    message: str
    data: T


class Course(BaseModel):
    template_project_id: UUID4 | None = None
    is_initialized: bool = False


class VirtualLabBase(BaseModel):
    name: str = Field(max_length=250)
    description: str
    reference_email: EmailStr | None = None
    email_verified: bool = False
    entity: str
    compute_cell: ComputeCell = ComputeCell.CELL_A


class VirtualLabUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    reference_email: EmailStr | None = None
    entity: str | None = None
    course: Course | None = None


class VirtualLabComputeCellUpdate(BaseModel):
    """Model for updating compute_cell - only accessible by service admins"""

    compute_cell: ComputeCell


class VirtualLabDetails(VirtualLabBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    created_at: datetime
    updated_at: datetime | None = None
    projects_count: int | None = None
    course: Course | None = None


class VirtualLab(VirtualLabBase):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: UUID4
    created_at: datetime
    updated_at: datetime | None = None
    projects_count: int | None = None
    created_by: UUID4
    email_verified: bool
    course: Course | None = None


class VirtualLabWithInviteDetails(VirtualLabDetails):
    model_config = ConfigDict(from_attributes=True)

    invite_id: UUID4


class VirtualLabUsers(BaseModel):
    owner_id: UUID4
    users: list[UserWithInviteStatus]
    total_active: int
    total: int


class VirtualLabStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    virtual_lab_id: UUID4
    total_projects: int
    total_members: int
    total_pending_invites: int
    admin_users: list[UUID4]
    member_users: list[UUID4]


class VirtualLabUser(BaseModel):
    user: UserWithInviteStatus


class VirtualLabOut(BaseModel):
    virtual_lab: VirtualLabDetails


class VirtualLabResponse(BaseModel):
    virtual_lab: VirtualLab
    admins: list[UUID4] | None = None


class VirtualLabWithAdmins(VirtualLab):
    admins: list[UUID4] | None = None
    owner: ShortenedUser | None = None


class VirtualLabDetailExpand(StrEnum):
    admins = auto()
    owner = auto()


class VirtualLabCreate(VirtualLabBase):
    course: Course | None = None


class CreateLabOut(BaseModel):
    virtual_lab: VirtualLabDetails


class SearchLabResponse(BaseModel):
    virtual_labs: list[VirtualLabDetails]


class InvitationResponse(BaseModel):
    id: UUID4


class ProjectVirtualLabMapping(BaseModel):
    project_id: UUID4
    virtual_lab_id: UUID4


class UserStats(BaseModel):
    """Statistics about a user's virtual labs and projects"""

    owned_labs_count: int
    member_labs_count: int
    pending_invites_count: int
    owned_projects_count: int
    member_projects_count: int
    total_labs: int
    total_projects: int
