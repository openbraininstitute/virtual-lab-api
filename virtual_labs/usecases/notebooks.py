from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.pagination import QueryPaginator
from virtual_labs.domain.common import (
    PaginatedResultsResponse,
)
from virtual_labs.domain.notebooks import Notebook as NotebookResult
from virtual_labs.domain.notebooks import NotebookCreate
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook


async def get_notebooks_usecase(
    project_id: UUID, query_paginator: QueryPaginator
) -> PaginatedResultsResponse[NotebookResult]:
    query = select(Notebook).where(Notebook.project_id == project_id)

    return await query_paginator.get_paginated_results(query, NotebookResult)


async def create_notebook_usecase(
    project_id: UUID,
    notebook_create: NotebookCreate,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
) -> NotebookResult:
    notebook = Notebook(**notebook_create.model_dump(), project_id=project_id)

    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)

    return NotebookResult.model_validate(notebook)
