from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

K = TypeVar("K")


class PaginatedDbResult(BaseModel, Generic[K]):
    count: int | None
    rows: K

    class Config:
        arbitrary_types_allowed = True


class UserRoleEnum(Enum):
    admin = "admin"
    member = "member"


T = TypeVar("T")


class VliAppResponse(BaseModel, Generic[T]):
    message: str
    data: T | None
