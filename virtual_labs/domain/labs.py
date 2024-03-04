from typing import Any, Optional
from pydantic import BaseModel, UUID4
from datetime import datetime


class VirtualLabBase(BaseModel):
    name: str
    description: str
    reference_email: str


class VirtualLabCreate(VirtualLabBase):
    pass


class VirtualLabUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    reference_email: str | None = None


class VirtualLab(VirtualLabBase):
    id: UUID4
    nexus_organization_id: str

    deleted: bool

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    projects: list[Any] = []

    class Config:
        orm_mode = True
