from pydantic import UUID4
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Bookmark


class BookmarkMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_bookmark(
        self, project_id: UUID4, resource_id: str, category: str
    ) -> Bookmark:
        bookmark = Bookmark(
            resource_id=resource_id, category=category, project_id=project_id
        )
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark
