from datetime import datetime
from typing import List, Optional

from pydantic import UUID4, BaseModel


class VirtualLabModel(BaseModel):
    id: UUID4
    name: str
    description: str

    class Config:
        from_attributes = True


class ProjectCreationModel(BaseModel):
    name: str
    description: Optional[str] = None
    include_members: Optional[list[UUID4]] = None


class Project(BaseModel):
    id: UUID4
    nexus_project_id: str
    admin_group_id: UUID4 | None
    member_group_id: UUID4 | None
    name: str
    description: str | None
    budget: float | None
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectVlOut(Project):
    virtual_lab: VirtualLabModel


class ProjectExistenceOut(BaseModel):
    exist: bool


class ProjectVLTuple(BaseModel):
    project: Project
    virtual_lab: VirtualLabModel


class ProjectVLTupleOut(BaseModel):
    projects: List[ProjectVlOut]
    total: int


class ProjectOut(BaseModel):
    project: Project


class ProjectsOut(BaseModel):
    project: List[Project]
    total: int


class ProjectDeletionOut(BaseModel):
    project_id: UUID4
    deleted: bool
    deleted_at: datetime


class ProjectBudgetOut(BaseModel):
    budget: float


class ProjectCountOut(BaseModel):
    count: int


class ProjectWithStarredDateOut(Project):
    starred_at: datetime
    starred: bool


class StarProjectsOut(BaseModel):
    projects: List[ProjectWithStarredDateOut]
    total: int


class ProjectUpdateBudgetOut(BaseModel):
    project_id: UUID4
    new_budget: float
    updated_at: datetime


class ProjectStarStatusUpdateOut(BaseModel):
    project_id: UUID4
    starred_at: datetime | None


class ProjectStar(BaseModel):
    id: UUID4

    class Config:
        from_attributes = True
