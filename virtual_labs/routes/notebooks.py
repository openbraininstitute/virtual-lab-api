from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from virtual_labs.core.authorization import verify_vlab_or_project_read_dep
from virtual_labs.core.pagination import QueryPaginator
from virtual_labs.core.types import VliAppResponse
from virtual_labs.domain.common import PaginatedResultsResponse
from virtual_labs.domain.notebooks import Notebook as NotebookResult
from virtual_labs.domain.notebooks import NotebookCreate
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.db.models import Notebook
from virtual_labs.usecases.notebooks import get_notebooks_usecase

router = APIRouter(prefix="/projects/{project_id}/notebooks", tags=["Notebooks"])


M = TypeVar("M", bound=DeclarativeBase)


@router.get("/", response_model=None)
async def list_notebooks(
    paginator: QueryPaginator = Depends(),
    auth_project_id: UUID = Depends(verify_vlab_or_project_read_dep),
) -> VliAppResponse[PaginatedResultsResponse[NotebookResult]]:
    notebooks = await get_notebooks_usecase(auth_project_id, paginator)
    return VliAppResponse(message="Found!", data=notebooks)


@router.post("/")
async def create_notebook(
    create_notebook: NotebookCreate,
    session: Annotated[AsyncSession, Depends(default_session_factory)],
    auth_project_id: UUID = Depends(verify_vlab_or_project_read_dep),
) -> VliAppResponse[NotebookResult]:
    stmt = (
        insert(Notebook)
        .values(**create_notebook.model_dump(), project_id=auth_project_id)
        .returning(Notebook)
    )

    res = (await session.execute(stmt)).scalar_one()

    return VliAppResponse(
        message="Notebook created successfully", data=NotebookResult.model_validate(res)
    )
