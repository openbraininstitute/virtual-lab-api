from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.pagination import PaginatedResults, QueryPaginator
from virtual_labs.domain.notebooks import Notebook as NotebookResult
from virtual_labs.domain.notebooks import NotebookCreate
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook


async def get_notebooks_usecase(
    project_id: UUID, query_paginator: QueryPaginator
) -> PaginatedResults[Notebook]:
    query = (
        select(Notebook)
        .where(Notebook.project_id == project_id)
        .order_by(desc(Notebook.created_at))
    )

    return await query_paginator.get_paginated_results(query)


async def create_notebook_usecase(
    project_id: UUID,
    notebook_create: NotebookCreate,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
) -> NotebookResult:
    try:
        notebook = Notebook(**notebook_create.model_dump(), project_id=project_id)

        session.add(notebook)
        await session.commit()
        await session.refresh(notebook)

        return NotebookResult.model_validate(notebook)
    except IntegrityError:
        raise VliError(
            message="Notebook already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            details="A notebook with that url already exists",
        )
