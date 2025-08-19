from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.pagination import PaginatedResults, QueryPaginator
from virtual_labs.domain.bookmark import BookmarkOut, EntityType
from virtual_labs.domain.common import PaginatedResultsResponse
from virtual_labs.domain.labs import LabResponse
from virtual_labs.infrastructure.db.models import Bookmark
from virtual_labs.repositories.bookmark_repo import BookmarkQueryRepository


async def get_bookmarks_by_category_paginated(
    db: AsyncSession,
    project_id: UUID4,
    category: EntityType,
    paginator: QueryPaginator,
) -> LabResponse[PaginatedResultsResponse[BookmarkOut]]:
    """
    Get paginated bookmarks for a specific project and category.

    Args:
        db: Database session
        project_id: Project UUID
        category: Required bookmark category
        paginator: Pagination parameters

    Returns:
        PaginatedResults containing BookmarkOut objects
    """
    try:
        repo = BookmarkQueryRepository(db)
        query = repo.get_project_bookmarks_by_category_query(project_id, category)

        paginated_db_results: PaginatedResults[
            Bookmark
        ] = await paginator.get_paginated_results(query)

        bookmark_outs: list[BookmarkOut] = [
            BookmarkOut.model_validate(db_bookmark)
            for db_bookmark in paginated_db_results["results"]
        ]

        return LabResponse(
            data=PaginatedResultsResponse(
                total=paginated_db_results["total"],
                page=paginated_db_results["page"],
                page_size=paginated_db_results["page_size"],
                results=bookmark_outs,
            ),
            message="Paginated bookmarks successfully retrieved for category",
        )

    except SQLAlchemyError as error:
        logger.error(
            f"DB error during retrieving paginated bookmarks for project: ({error})"
        )
        raise VliError(
            message="Failed to retrieve paginated bookmarks",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        logger.exception(
            f"Error during retrieving paginated bookmarks for project: ({error})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Retrieving paginated bookmarks failed",
            details=str(error),
        )
