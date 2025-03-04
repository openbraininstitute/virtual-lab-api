from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import Annotated

from virtual_labs.domain.labs import VirtualLabWithInviteDetails


class PageParams(BaseModel):
    page: Annotated[int, Field(strict=True, ge=1)] = 1
    size: Annotated[int, Field(strict=True, ge=1)] = 50


T = TypeVar("T")
K = TypeVar("K")


class PaginatedResultsResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    results: list[T]


class LabListWithPending(BaseModel, Generic[T]):
    pending_labs: List[VirtualLabWithInviteDetails]
    virtual_lab: T | None
    members_count: int | None
    projects_count: int | None
