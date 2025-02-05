from typing import Annotated, Generic, TypedDict, TypeVar

from fastapi import Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.selectable import Select

from virtual_labs.infrastructure.db.config import default_session_factory

M = TypeVar("M", bound=DeclarativeBase)


class PaginatedResults(TypedDict, Generic[M]):
    total: int
    page: int
    page_size: int
    results: list[M]


class QueryPaginator:
    def __init__(
        self,
        session: Annotated[AsyncSession, Depends(default_session_factory)],
        page: Annotated[
            int, Query(ge=1, description="Page number, starting from 1")
        ] = 1,
        page_size: Annotated[
            int,
            Query(ge=1, le=100, description="Number of items per page (1-100)"),
        ] = 50,
    ):
        self.page = page
        self.size = page_size
        self.session = session

    def total_query(self, query: Select[tuple[M]]) -> Select[tuple[int]]:
        return query.with_only_columns(func.coalesce(func.count(), 0)).order_by(None)

    def paginate_query(self, query: Select[tuple[M]]) -> Select[tuple[M]]:
        return query.offset((self.page - 1) * self.size).limit(self.size)

    async def get_paginated_results(
        self, query: Select[tuple[M]]
    ) -> PaginatedResults[M]:
        paginated_query = self.paginate_query(query)

        total_query = self.total_query(query)
        total_result = await self.session.execute(total_query)
        result = await self.session.execute(paginated_query)
        results = list(result.scalars().all())

        return PaginatedResults(
            total=total_result.scalar() or 0,
            page=self.page,
            page_size=len(results),
            results=results,
        )
