from http import HTTPStatus
from typing import List

from pydantic import UUID4
from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.domain.bookmark import DeleteBookmarkIn
from virtual_labs.repositories.bookmark_repo import BookmarkMutationRepository


async def core_delete_bookmarks(
    db: AsyncSession,
    project_id: UUID4,
    bookmarks: List[DeleteBookmarkIn],
) -> None:
    repo = BookmarkMutationRepository(db)

    try:
        await repo.delete_bookmarks_bulk(
            project_id=project_id,
            bookmarks_to_delete=bookmarks,
        )

    except NoResultFound as error:
        raise VliError(
            message="No bookmark with these parameters was found in this project",
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            details=str(error),
        )
    except SQLAlchemyError as error:
        raise VliError(
            message="The bookmark could not be deleted",
            error_code=VliErrorCode.DATABASE_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(error),
        )
    except Exception as error:
        raise VliError(
            error_code=VliErrorCode.SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="Adding bookmark to project failed",
            details=str(error),
        )
