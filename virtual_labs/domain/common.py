from typing import Generic, TypeVar
from typing_extensions import Annotated

from pydantic import BaseModel, Field


class PageParams(BaseModel):
    page: Annotated[int, Field(strict=True, ge=1)] = 1
    size: Annotated[int, Field(strict=True, ge=1)] = 50


T = TypeVar("T")


class PagedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    results: list[T]
