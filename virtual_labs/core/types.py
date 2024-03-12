from enum import Enum
from typing import Generic, TypedDict, TypeVar

from pydantic import BaseModel


class Pagination(TypedDict):
    page: int
    size: int
    total: int


class UserRoleEnum(Enum):
    admin = "admin"
    member = "member"


T = TypeVar("T")


class VliAppResponse(BaseModel, Generic[T]):
    message: str
    data: T | None
