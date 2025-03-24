from enum import Enum
from typing import Generic, Optional, TypedDict, TypeVar

from pydantic import BaseModel, ConfigDict

K = TypeVar("K")


class PaginatedDbResult(BaseModel, Generic[K]):
    count: int
    rows: K

    class Config:
        arbitrary_types_allowed = True


class UserRoleEnum(Enum):
    admin = "admin"
    member = "member"


class UserGroup(BaseModel):
    """User Group representation"""

    group_id: str
    name: str
    group_type: str  # "vlab" or "project"
    project_id: Optional[str] = None  # Project ID (only for project type)
    virtual_lab_id: Optional[str] = None  # Virtual lab ID
    role: UserRoleEnum  # admin or  member

    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Response(TypedDict, Generic[T]):
    message: str
    data: T


class VliAppResponse(BaseModel, Generic[T]):
    message: str
    data: T | None
