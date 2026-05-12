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


class Pagination(BaseModel):
    """Generic pagination envelope shared by list endpoints.

    Fields are derived once at response time and are the canonical
    "where am I in the result set" view — they let UIs render
    page-X-of-Y indicators and next/previous controls without
    additional bookkeeping.
    """

    page: int
    size: int
    page_size: int
    total: int
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard list-endpoint payload: `{data: [...], pagination: {...}}`.

    Use as the inner payload (under `VliResponse.new(data=...)`) for any
    paginated collection. The generic parameter is the item type.
    """

    data: list[T]
    pagination: Pagination

    @classmethod
    def build(
        cls, *, items: list[T], total: int, page: int, size: int
    ) -> "PaginatedResponse[T]":
        return cls(
            data=items,
            pagination=Pagination(
                page=page,
                size=size,
                page_size=len(items),
                total=total,
                has_next=(page * size) < total,
                has_previous=page > 1,
            ),
        )


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
    pending_labs: List[VirtualLabWithInviteDetails] | None = None
    membership_labs: PaginatedResponse[VirtualLabDetails] | None = None
    admin_labs: PaginatedResponse[VirtualLabDetails] | None = None
    virtual_lab: VirtualLabDetails | None = None
