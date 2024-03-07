from datetime import datetime
from typing import List, Optional

from pydantic import UUID4, BaseModel


class ProjectCreationModel(BaseModel):
    name: str
    description: Optional[str] = None
    include_members: Optional[list[UUID4]] = None


class Project(BaseModel):
    id: UUID4
    nexus_project_id: str
    name: str
    description: str | None
    budget: float | None
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ProjectExistenceOut(BaseModel):
    exist: bool


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
