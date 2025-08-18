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
) -> list[EntityType]:
    """
    Get all distinct bookmark categories for a specific project.

    Args:
        db: Database session
        project_id: Project UUID

    Returns:
        List of EntityType enums used in the project
    """
    try:
        repo = BookmarkQueryRepository(db)
        category_strings: list[str] = await repo.get_project_categories(project_id)

        # Convert string values to EntityType enums
        categories: list[EntityType] = [
            EntityType(category_str) for category_str in category_strings
        ]

        return categories

    except SQLAlchemyError as error:
        logger.error(f"DB error during retrieving categories for project: ({error})")
        raise VliError(
            message="Failed to retrieve project categories",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        logger.exception(f"Error during retrieving categories for project: ({error})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Retrieving project categories failed",
            details=str(error),
        )
