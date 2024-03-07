from enum import Enum
from typing import Generic, TypedDict, TypeVar

from pydantic import BaseModel


class Pagination(TypedDict):
    page: int
    size: int
    total: int


class User(Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


T = TypeVar("T")


class VliAppResponse(BaseModel, Generic[T]):
    message: str
    data: T | None
