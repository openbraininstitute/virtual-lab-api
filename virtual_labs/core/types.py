from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

K = TypeVar("K")


class PaginatedDbResult(BaseModel, Generic[K]):
    count: int
    rows: K

    class Config:
        arbitrary_types_allowed = True


class UserRoleEnum(Enum):
    admin = "admin"
    member = "member"


T = TypeVar("T")


@dataclass
class VliAppResponseType(Generic[T]):
    message: str
    data: T | None


class VliAppResponse(BaseModel, Generic[T]):
    message: str
    data: T | None
