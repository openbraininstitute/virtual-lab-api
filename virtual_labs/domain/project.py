from datetime import datetime
from typing import Optional

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
