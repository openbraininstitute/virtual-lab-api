from typing import Annotated, Generic, TypedDict, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.selectable import Select

from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.common import PageParams, PaginatedResultsResponse
from virtual_labs.domain.notebooks import NotebookRead
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook

router = APIRouter(prefix="/projects/{project_id}/notebooks", tags=["Notebooks"])

T = TypeVar("T")

ModelType = TypeVar("ModelType", bound=DeclarativeBase)


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
    page_parms: PageParams

    def __init__(
        self,
        page_params: Annotated[PageParams, Depends()],
        session: Annotated[AsyncSession, Depends(default_session_factory)],
    ):
        self.page_params = page_params
        self.session = session

    def total_query(self, query: Select[tuple[ModelType]]) -> Select[tuple[int]]:
        return query.with_only_columns(func.coalesce(func.count(), 0)).order_by(None)

    def paginate_query(
        self, query: Select[tuple[ModelType]]
    ) -> Select[tuple[ModelType]]:
        return query.offset((self.page_parms.page - 1) * self.page_params.size).limit(
            self.page_parms.size
        )

    async def get_paginated_response(
        self, query: Select[tuple[ModelType]]
    ) -> PaginatedResponse[ModelType]:
        paginated_query = self.paginate_query(query)

        total_query = self.total_query(query)
        total_result = await self.session.execute(total_query)
        result = await self.session.execute(paginated_query)
        return {
            "message": "Success",
            "data": {
                "total": total_result.scalar() or 0,
                "page": self.page_params.page,
                "page_size": self.page_params.size,
                "results": list(result.scalars().all()),
            },
        }


@router.get("/", response_model=VliAppResponse[PaginatedResultsResponse[NotebookRead]])
async def list_notebooks(
    project_id: UUID,
    pagination: Annotated[QueryPagination, Depends()],
) -> PaginatedResponse[Notebook]:
    query = select(Notebook).where(Notebook.project_id == project_id)

    return await pagination.get_paginated_response(query)
