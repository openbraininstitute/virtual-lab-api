from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import Annotated

from virtual_labs.domain.labs import VirtualLabDetails, VirtualLabWithInviteDetails


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


class DbPagination(BaseModel, Generic[T]):
    total: int
    filtered_total: int | None = None
    page: int
    size: int
    page_size: int
    results: list[T]
    has_next: bool
    has_previous: bool

    model_config = {"arbitrary_types_allowed": True}


class VirtualLabResponse(BaseModel):
    pending_labs: List[VirtualLabWithInviteDetails] | None
    membership_labs: DbPagination[VirtualLabDetails] | None
    virtual_lab: VirtualLabDetails | None
