from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, Query
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.authorization.verify_vlab_or_project_read import (
    verify_vlab_or_project_read,
)
from virtual_labs.core.pagination import QueryPaginator
from virtual_labs.domain.bookmark import (
    BookmarkIn,
    BookmarkOut,
    BulkDeleteBookmarks,
    DeleteBookmarkIn,
    EntityType,
)
from virtual_labs.domain.common import PaginatedResultsResponse
from virtual_labs.domain.labs import LabResponse
from virtual_labs.infrastructure.db.config import default_session_factory
from virtual_labs.infrastructure.kc.auth import a_verify_jwt, verify_jwt
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
    incoming_bookmark: BookmarkIn,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[BookmarkOut]:
    result = await usecases.add_bookmark(session, project_id, incoming_bookmark)
    return LabResponse[BookmarkOut](
        message="Resource successfully bookmarked to project",
        data=result,
    )


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks",
    summary="Get project bookmarks by category",
    response_model=LabResponse[dict[EntityType, list[BookmarkOut]]],
)
@verify_vlab_or_project_read
async def get_bookmarks_by_category(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    category: EntityType | None = Query(None, description="category"),
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[dict[EntityType, list[BookmarkOut]]]:
    result = await usecases.get_bookmarks_by_category(session, project_id, category)
    return LabResponse[dict[EntityType, list[BookmarkOut]]](
        message="Bookmarks successfully retrieved for project", data=result
    )


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks/bulk-delete",
    summary="Bulk delete bookmarks by category and resource id",
    response_model=LabResponse[BulkDeleteBookmarks],
)
@verify_vlab_or_project_read
async def bulk_delete_bookmarks(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    bookmarks_to_delete: list[BookmarkIn],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[BulkDeleteBookmarks]:
    result = await usecases.bulk_delete_bookmarks(
        session, project_id, bookmarks_to_delete
    )
    return LabResponse[BulkDeleteBookmarks](
        message="Bulk delete bookmarks", data=result
    )


@router.delete(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks",
    summary="Delete bookmark by category and resource id",
    response_model=LabResponse[None],
)
@verify_vlab_or_project_read
async def delete_bookmark(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    entity_id: UUID4,
    category: EntityType,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[None]:
    await usecases.delete_bookmark(session, project_id, entity_id, category)
    return LabResponse[None](message="Bulk delete bookmarks", data=None)


@router.post(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks/delete",
    summary="Delete bookmark by category and resource id",
    response_model=LabResponse[None],
)
@verify_vlab_or_project_read
async def core_delete_bookmark(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    bookmarks: Annotated[List[DeleteBookmarkIn], Body(embed=True)],
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(a_verify_jwt),
) -> LabResponse[None]:
    await usecases.core_delete_bookmarks(
        session,
        project_id,
        bookmarks,
    )
    return LabResponse[None](message="Bulk delete bookmarks", data=None)


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks/paginated",
    summary="Get paginated bookmarks by category",
    response_model=LabResponse[PaginatedResultsResponse[BookmarkOut]],
)
@verify_vlab_or_project_read
async def get_bookmarks_by_category_paginated(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    category: EntityType = Query(..., description="Required bookmark category"),
    paginator: QueryPaginator = Depends(),
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[PaginatedResultsResponse[BookmarkOut]]:
    result = await usecases.get_bookmarks_by_category_paginated(
        session, project_id, category, paginator
    )
    return result


@router.get(
    "/{virtual_lab_id}/projects/{project_id}/bookmarks/categories",
    summary="Get all bookmark categories for a project",
    response_model=LabResponse[list[EntityType]],
)
@verify_vlab_or_project_read
async def get_project_categories(
    virtual_lab_id: UUID4,
    project_id: UUID4,
    session: AsyncSession = Depends(default_session_factory),
    auth: tuple[AuthUser, str] = Depends(verify_jwt),
) -> LabResponse[list[EntityType]]:
    result = await usecases.get_project_categories(session, project_id)
    return LabResponse[list[EntityType]](
        message="Project categories successfully retrieved", data=result
    )
