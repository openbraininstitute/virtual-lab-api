from typing import Any, Optional, TypeVar, Generic
from pydantic import BaseModel, UUID4
from datetime import datetime


T = TypeVar("T")


class LabResponse(BaseModel, Generic[T]):
    message: str
    data: T


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


class VirtualLabDomain(VirtualLabBase):
    id: UUID4
    nexus_organization_id: str

    deleted: bool

    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    projects: list[Any] = []

    class Config:
        from_attributes = True
