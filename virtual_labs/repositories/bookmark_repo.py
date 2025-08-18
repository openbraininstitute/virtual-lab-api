from pydantic import UUID4
from sqlalchemy import and_, delete, distinct, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from virtual_labs.domain.bookmark import DeleteBookmarkIn, EntityType
from virtual_labs.infrastructure.db.models import Bookmark


class BookmarkQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project_bookmarks(
        self,
        project_id: UUID4,
        category: EntityType | None = None,
    ) -> list[Bookmark]:
        query = select(Bookmark).where(Bookmark.project_id == project_id)

        if category is not None:
            query = query.where(Bookmark.category == category)

        result = (await self.session.execute(statement=query)).scalars().all()
        return list(result)

    def get_project_bookmarks_by_category_query(
        self,
        project_id: UUID4,
        category: EntityType,
    ) -> Select[tuple[Bookmark]]:
        """
        Returns a SQLAlchemy query for getting bookmarks by project and category
        for pagination purposes.
        """
        return select(Bookmark).where(
            and_(Bookmark.project_id == project_id, Bookmark.category == category)
        )

    async def get_project_categories(
        self,
        project_id: UUID4,
    ) -> list[str]:
        """
        Get all distinct categories for a specific project.
        """
        query = select(distinct(Bookmark.category)).where(
            Bookmark.project_id == project_id
        )
        result = (await self.session.execute(statement=query)).scalars().all()
        return list(result)


class BookmarkMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_bookmark(
        self,
        project_id: UUID4,
        category: str,
        entity_id: UUID4 | None = None,
    ) -> Bookmark:
        bookmark = Bookmark(
            entity_id=entity_id,
            category=category,
            project_id=project_id,
        )
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def delete_bookmark_by_params(
        self,
        project_id: UUID4,
        entity_id: UUID4,
        category: str,
    ) -> UUID4:
        query = (
            delete(Bookmark)
            .where(
                and_(
                    Bookmark.project_id == project_id,
                    Bookmark.category == category,
                    Bookmark.entity_id == entity_id,
                )
            )
            .returning(
                Bookmark.id,
            )
        )
        result = await self.session.execute(statement=query)
        await self.session.commit()
        return result.scalar_one()

    async def delete_bookmarks_bulk(
        self,
        bookmarks_to_delete: list[DeleteBookmarkIn],
        project_id: UUID4,
    ) -> int:
        """
        delete multiple bookmarks in a single database operation.
        Args:
            db_session: AsyncSession - The async SQLAlchemy session
            bookmarks_to_delete: list[BookmarkIn] - List of bookmark objects to delete
            project_id: UUID - The project ID these bookmarks belong to

        Returns:
            int: Number of bookmarks deleted
        """
        if not bookmarks_to_delete:
            return 0

        delete_conditions = []
        for bookmark in bookmarks_to_delete:
            full_condition = and_(
                Bookmark.entity_id == bookmark.entity_id,
                Bookmark.category == bookmark.category,
                Bookmark.project_id == project_id,
            )

            delete_conditions.append(full_condition)

        if not delete_conditions:
            return 0

        combined_condition = or_(*delete_conditions)
        stmt = delete(Bookmark).where(combined_condition)

        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.rowcount
