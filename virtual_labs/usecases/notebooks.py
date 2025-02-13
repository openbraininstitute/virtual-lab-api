from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.pagination import PaginatedResults, QueryPaginator
from virtual_labs.domain.notebooks import Notebook as NotebookResult
from virtual_labs.domain.notebooks import NotebookBulkCreate, NotebookCreate
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook
from virtual_labs.repositories.notebook_repo import (
    bulk_create_notebook,
    create_notebook,
    delete_notebook,
    get_notebooks,
)


async def get_notebooks_usecase(
    project_id: UUID, query_paginator: QueryPaginator
) -> PaginatedResults[Notebook]:
    query = get_notebooks(project_id)
    return await query_paginator.get_paginated_results(query)


async def create_notebook_usecase(
    project_id: UUID,
    notebook_create: NotebookCreate,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
) -> NotebookResult:
    try:
        notebook = create_notebook(notebook_create, project_id)
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


async def bulk_create_notebooks_usecase(
    project_id: UUID,
    notebook_create: NotebookBulkCreate,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
) -> list[NotebookResult]:
    try:
        stmt = bulk_create_notebook(notebook_create, project_id)
        result = await session.execute(stmt)
        await session.commit()
        notebooks = result.scalars().all()
        return [NotebookResult.model_validate(notebook) for notebook in notebooks]
    except IntegrityError:
        raise VliError(
            message="Notebook already exists",
            error_code=VliErrorCode.ENTITY_ALREADY_EXISTS,
            http_status_code=HTTPStatus.CONFLICT,
            details="A notebook with that url already exists",
        )


async def delete_notebook_usecase(
    project_id: UUID,
    notebook_id: UUID,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
) -> None:
    q = delete_notebook(notebook_id, project_id)
    result = await session.execute(q)

    await session.commit()

    if result.rowcount == 0:
        raise VliError(
            message="Notebook doesn't exist",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            details="Notebook doesn't exist in the specified project",
        )

    return None
