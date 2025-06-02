from pydantic import UUID4
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.infrastructure.db.models import Bookmark


class BookmarkQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project_bookmarks(self, project_id: UUID4) -> list[Bookmark]:
        query = select(Bookmark).where(Bookmark.project_id == project_id)
        result = (await self.session.execute(statement=query)).scalars().all()
        return list(result)


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

    async def delete_bookmark_by_params(
        self, project_id: UUID4, resource_id: str, category: str
    ) -> UUID4:
        query = (
            delete(Bookmark)
            .where(
                and_(
                    Bookmark.project_id == project_id,
                    Bookmark.resource_id == resource_id,
                    Bookmark.category == category,
                )
            )
            .returning(
                Bookmark.id,
            )
        )
        result = await self.session.execute(statement=query)
        await self.session.commit()
        return result.scalar_one()
