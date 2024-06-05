from http import HTTPStatus

from loguru import logger
from pydantic import UUID4
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.bookmark import BookmarkIn, BookmarkOut
from virtual_labs.repositories.bookmark_repo import BookmarkMutationRepository


async def add_bookmark(
    db: AsyncSession, project_id: UUID4, payload: BookmarkIn
) -> BookmarkOut:
    try:
        repo = BookmarkMutationRepository(db)
        bookmark = await repo.add_bookmark(
            project_id, payload.resource_id, payload.category.value
        )
        return BookmarkOut.model_validate(bookmark)
    except SQLAlchemyError as error:
        logger.error(f"DB error during adding bookmark to project: ({error})")
        raise VliError(
            message="The bookmark could not be added",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        logger.exception(f"Error during adding bookmark to project: ({error})")
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding bookmark to project failed",
            details=str(error),
        )
