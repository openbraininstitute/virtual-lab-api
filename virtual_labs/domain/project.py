from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
)

from virtual_labs.core.types import UserRoleEnum
from virtual_labs.domain.user import UserWithInviteStatus


class VirtualLabModel(BaseModel):
    id: UUID4
    name: str
    description: str

    class Config:
        from_attributes = True


class ProjectBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)
    ]
    description: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = None


class ProjectUpdateBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)
        ]
    ] = None
    description: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = None


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    nexus_project_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime | None


class ProjectVlOut(Project):
    virtual_lab_id: UUID4
    user_count: int = 0


class ProjectStats(BaseModel):
    project_id: UUID4
    total_stars: int
    total_bookmarks: int
    total_pending_invites: int
    total_members: int
    total_notebooks: int
    admin_users: list[UUID4]
    member_users: list[UUID4]

    class Config:
        from_attributes = True


class ProjectExistenceOut(BaseModel):
    exist: bool


class ProjectWithVLOut(BaseModel):
    projects: List[ProjectVlOut]
    total: int


class FailedInvite(BaseModel):
    user_email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    exists: bool = True


class ProjectOut(BaseModel):
    project: ProjectVlOut
    failed_invites: List[FailedInvite]


class ProjectsOut(BaseModel):
    project: List[Project]
    total: int


class ProjectDeletionOut(BaseModel):
    project_id: UUID4
    deleted: bool
    deleted_at: datetime


class ProjectCountOut(BaseModel):
    count: int


class ProjectWithStarredDateOut(ProjectVlOut):
    updated_at: datetime
    starred_at: bool


class ProjectUpdateBudgetOut(BaseModel):
    project_id: UUID4
    new_budget: float
    updated_at: datetime


class ProjectUpdateRoleOut(BaseModel):
    project_id: UUID4
    new_role: UserRoleEnum


class ProjectUserDeleteOut(BaseModel):
    project_id: UUID4
    deleted: bool
    deleted_at: datetime


class ProjectStarStatusUpdateOut(BaseModel):
    project_id: UUID4
    starred_at: datetime | None


class ProjectStar(BaseModel):
    id: UUID4
    user_id: UUID4

    class Config:
        from_attributes = True


class ProjectUsersOut(BaseModel):
    users: List[UserWithInviteStatus]
    total: int


class ProjectUsersCountOut(BaseModel):
    project_id: UUID4
    total: int


class ProjectPerVLCountOut(BaseModel):
    virtual_lab_id: UUID4
    total: int


class ProjectInviteIn(BaseModel):
    email: EmailStr
    role: UserRoleEnum


class AddUserToProjectIn(BaseModel):
    id: UUID4
    email: EmailStr
    role: UserRoleEnum


class ProjectInviteOut(BaseModel):
    origin: str = "Project"
    invite_id: UUID4


class AddUserProjectDetails(BaseModel):
    """User details with role information for a project"""

    id: str
    email: EmailStr
    role: UserRoleEnum


class EmailFailure(BaseModel):
    """Email sending failure details"""

    email: EmailStr
    error: str


class AttachUserFailedOperation(BaseModel):
    user_id: UUID4
    requested_role: UserRoleEnum
    error: str


class ProjectUserOperationsResponse(BaseModel):
    """Response model for project user operations"""

    project_id: UUID4
    added_users: List[AddUserProjectDetails]
    updated_users: List[AddUserProjectDetails]
    failed_operations: List[AttachUserFailedOperation]
    email_sending_failures: List[EmailFailure]
    processed_at: datetime = datetime.now()


class ProjectCreationBody(ProjectBody):
    include_members: Optional[List[AddUserToProjectIn]] = None
