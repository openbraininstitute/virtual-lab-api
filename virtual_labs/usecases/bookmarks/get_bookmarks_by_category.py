from collections import defaultdict
from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.bookmark import BookmarkOut, EntityType
from virtual_labs.repositories.bookmark_repo import BookmarkQueryRepository


async def get_bookmarks_by_category(
    db: AsyncSession,
    project_id: UUID4,
    category: EntityType | None = None,
) -> dict[EntityType, list[BookmarkOut]]:
    try:
        repo = BookmarkQueryRepository(db)
        db_bookmarks = await repo.get_project_bookmarks(project_id, category)

        grouped_bookmarks: defaultdict[EntityType, list[BookmarkOut]] = defaultdict(
            list
        )

        for db_bookmark in db_bookmarks:
            grouped_bookmarks[EntityType(db_bookmark.category)].append(
                BookmarkOut.model_validate(db_bookmark)
            )

        return grouped_bookmarks
    except SQLAlchemyError as error:
        logger.error(f"DB error during retrieving bookmarks for project: ({error})")
        raise VliError(
            message="The bookmark could not be added",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        logger.exception(f"Error during retrieving bookmarks for project: ({error})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding bookmark to project failed",
            details=str(error),
        )
