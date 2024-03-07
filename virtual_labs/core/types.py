from enum import Enum
from typing import TypedDict


class Pagination(TypedDict):
    page: int
    size: int
    total: int


class User(Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
