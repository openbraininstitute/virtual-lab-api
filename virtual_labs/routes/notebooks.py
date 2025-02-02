from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization import verify_vlab_or_project_read_dep
from virtual_labs.core.pagination import QueryPaginator
from virtual_labs.core.types import Response, VliAppResponse
from virtual_labs.domain.common import PaginatedResultsResponse
from virtual_labs.domain.notebooks import Notebook as NotebookResult
from virtual_labs.domain.notebooks import NotebookCreate
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.usecases.notebooks import (
    create_notebook_usecase,
    get_notebooks_usecase,
)

router = APIRouter(prefix="/projects/{project_id}/notebooks", tags=["Notebooks"])


@router.get(
    "/",
)
async def list_notebooks(
    paginator: QueryPaginator = Depends(),
    auth_project_id: UUID = Depends(verify_vlab_or_project_read_dep),
) -> VliAppResponse[PaginatedResultsResponse[NotebookResult]]:
    notebooks = await get_notebooks_usecase(auth_project_id, paginator)
    return Response(message="Found!", data=notebooks)  # type: ignore[return-value]


@router.post("/")
async def create_notebook(
    create_notebook: NotebookCreate,
    session: AsyncSession = Depends(default_session_factory),
    auth_project_id: UUID = Depends(verify_vlab_or_project_read_dep),
) -> VliAppResponse[NotebookResult]:
    res = await create_notebook_usecase(auth_project_id, create_notebook, session)

    return Response(message="Notebook created successfully", data=res)  # type: ignore[return-value]
