from fastapi import APIRouter, Depends
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_vlab_or_project_read import (
    verify_vlab_or_project_read,
)
from virtual_labs.domain.bookmark import AddBookmarkBody, BookmarkCategory, BookmarkOut
from virtual_labs.domain.labs import LabResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import verify_jwt
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.usecases import bookmarks as usecases

router = APIRouter(
    prefix="/virtual-labs",
    tags=["Bookmarks Endpoints"],
)


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks",
    summary="Pin/bookmark a resource to a project",
    response_model=LabResponse[BookmarkOut],
)
@verify_vlab_or_project_read
async def add_bookmark(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    incoming_bookmark: AddBookmarkBody,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[BookmarkOut]:
    result = await usecases.add_bookmark(session, project_id, incoming_bookmark)
    return LabResponse[BookmarkOut](
        message="Resource successfully bookmarked to project", data=result
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks",
    summary="Get project bookmarks by category",
    response_model=LabResponse[dict[BookmarkCategory, list[BookmarkOut]]],
)
@verify_vlab_or_project_read
async def get_bookmarks_by_category(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[dict[BookmarkCategory, list[BookmarkOut]]]:
    result = await usecases.get_bookmarks_by_category(session, project_id)
    return LabResponse[dict[BookmarkCategory, list[BookmarkOut]]](
        message="Resource successfully bookmarked to project", data=result
    )
