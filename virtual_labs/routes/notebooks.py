from typing import Annotated, Generic, TypedDict, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.selectable import Select

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.common import PaginatedResultsResponse
from virtual_labs.domain.notebooks import NotebookRead
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook

router = APIRouter(prefix="/projects/{project_id}/notebooks", tags=["Notebooks"])


T = TypeVar("T")
M = TypeVar("M", bound=DeclarativeBase)


class VLResponse(TypedDict, Generic[T]):
    message: str
    data: T


class Paginated(TypedDict, Generic[T]):
    total: int
    page: int
    page_size: int
    results: list[T]


class PaginatedResponse(TypedDict, Generic[T]):
    message: str
    data: Paginated[T]


class QueryPagination:
    def __init__(
        self,
        session: Annotated[AsyncSession, Depends(default_session_factory)],
        page: Annotated[
            int, Query(ge=1, description="Page number, starting from 1")
        ] = 1,
        size: Annotated[
            int,
            Query(ge=1, le=100, description="Number of items per page (1-100)"),
        ] = 50,
    ):
        self.page = page
        self.size = size
        self.session = session

    def total_query(self, query: Select[tuple[M]]) -> Select[tuple[int]]:
        return query.with_only_columns(func.coalesce(func.count(), 0)).order_by(None)

    def paginate_query(self, query: Select[tuple[M]]) -> Select[tuple[M]]:
        return query.offset((self.page - 1) * self.size).limit(self.size)

    async def get_paginated_response(
        self, query: Select[tuple[M]]
    ) -> PaginatedResponse[M]:
        paginated_query = self.paginate_query(query)

        total_query = self.total_query(query)
        total_result = await self.session.execute(total_query)
        result = await self.session.execute(paginated_query)
        return {
            "message": "Success",
            "data": {
                "total": total_result.scalar() or 0,
                "page": self.page,
                "page_size": self.size,
                "results": list(result.scalars().all()),
            },
        }


@router.get("/", response_model=VliAppResponse[PaginatedResultsResponse[NotebookRead]])
async def list_notebooks(
    project_id: UUID,
    pagination: QueryPagination = Depends(),
) -> PaginatedResponse[Notebook]:
    query = select(Notebook).where(Notebook.project_id == project_id)

    res = await pagination.get_paginated_response(query)
    return res
