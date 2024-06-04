from loguru import logger
from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.domain.bookmark import AddBookmarkBody, BulkDeleteBookmarks
from virtual_labs.repositories.bookmark_repo import BookmarkMutationRepository


async def bulk_delete_bookmarks(
    db: AsyncSession, project_id: UUID4, bookmarks: list[AddBookmarkBody]
) -> BulkDeleteBookmarks:
    result: BulkDeleteBookmarks = {"successfully_deleted": [], "failed_to_delete": []}
    repo = BookmarkMutationRepository(db)

    for bookmark in bookmarks:
        try:
            await repo.delete_bookmark_by_params(
                project_id, bookmark.resource_id, bookmark.category.value
            )
            result["successfully_deleted"].append(bookmark)
        except Exception as error:
            logger.error(
                f"DB error during deleting bookmark from project {bookmark.resource_id} {bookmark.category}: ({error})"
            )
            result["failed_to_delete"].append(bookmark)

    return result
