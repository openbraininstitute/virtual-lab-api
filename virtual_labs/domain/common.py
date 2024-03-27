from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import Annotated


class PageParams(BaseModel):
    page: Annotated[int, Field(strict=True, ge=1)] = 1
    size: Annotated[int, Field(strict=True, ge=1)] = 50


T = TypeVar("T")


class PaginatedResultsResponse(BaseModel, Generic[T]):
    total: int
    page: int
    size: int
    page_size: int
    results: list[T]
