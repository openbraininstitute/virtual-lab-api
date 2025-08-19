from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.bookmark import EntityType
from virtual_labs.repositories.bookmark_repo import BookmarkQueryRepository


async def get_project_categories(
    db: AsyncSession,
    project_id: UUID4,
) -> dict[EntityType, int]:
    """
    Get count of bookmarks by category for a specific project.

    Args:
        db: Database session
        project_id: Project UUID

    Returns:
        Dictionary with EntityType as keys and counts as values
    """
    try:
        repo = BookmarkQueryRepository(db)
        category_counts_str = await repo.get_project_category_counts(project_id)

        # Convert string keys to EntityType enums
        category_counts: dict[EntityType, int] = {
            EntityType(category_str): count
            for category_str, count in category_counts_str.items()
        }

        return category_counts

    except SQLAlchemyError as error:
        logger.error(
            f"DB error during retrieving category counts for project: ({error})"
        )
        raise VliError(
            message="Failed to retrieve project category counts",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        logger.exception(
            f"Error during retrieving category counts for project: ({error})"
        )
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Retrieving project category counts failed",
            details=str(error),
        )
