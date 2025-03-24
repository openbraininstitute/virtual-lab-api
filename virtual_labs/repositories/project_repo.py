from datetime import datetime
from typing import List, Tuple, cast
from uuid import UUID

from pydantic import UUID4
from sqlalchemy import Row, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload
from sqlalchemy.sql import and_

from virtual_labs.core.types import PaginatedDbResult
from virtual_labs.domain.common import PageParams
from virtual_labs.domain.project import (
    ProjectCreationBody,
    ProjectUpdateBody,
)
from virtual_labs.infrastructure.db.models import (
    Bookmark,
    Notebook,
    Project,
    ProjectInvite,
    ProjectStar,
    VirtualLab,
)


class ProjectQueryRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project_stats(
        self,
        project_id: UUID,
    ) -> dict[str, int]:
        """Get statistics for a project using a single optimized query."""
        from sqlalchemy import distinct, func, select

        # Filter Project first
        base_query = (
            select(Project).where(
                Project.id == project_id,
                ~Project.deleted,
            )
        ).subquery()

        stats_query = (
            select(
                base_query.c.id,
                func.count(distinct(ProjectStar.id)).label("total_stars"),
                func.count(distinct(Bookmark.id)).label("total_bookmarks"),
                func.count(distinct(ProjectInvite.id))
                .filter(~ProjectInvite.accepted)
                .label("total_pending_invites"),
                func.count(distinct(Notebook.id)).label("total_notebooks"),
            )
            .select_from(base_query)
            .outerjoin(ProjectStar, base_query.c.id == ProjectStar.project_id)
            .outerjoin(Bookmark, base_query.c.id == Bookmark.project_id)
            .outerjoin(ProjectInvite, base_query.c.id == ProjectInvite.project_id)
            .outerjoin(Notebook, base_query.c.id == Notebook.project_id)
            .group_by(base_query.c.id)
        )

        result = await self.session.execute(stats_query)
        stats = result.first()

        if not stats:
            return {
                "total_stars": 0,
                "total_bookmarks": 0,
                "total_pending_invites": 0,
                "total_notebooks": 0,
            }

        return {
            "total_stars": stats.total_stars,
            "total_bookmarks": stats.total_bookmarks,
            "total_pending_invites": stats.total_pending_invites,
            "total_notebooks": stats.total_notebooks,
        }

    async def retrieve_projects_per_vl_batch(
        self,
        virtual_lab_id: UUID4,
        groups: List[str],
        pagination: PageParams,
    ) -> PaginatedDbResult[List[Row[Tuple[Project, VirtualLab]]]]:
        query = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(
                    or_(
                        Project.admin_group_id.in_(groups),
                        Project.member_group_id.in_(groups),
                    ),
                    Project.virtual_lab_id == virtual_lab_id,
                    ~Project.deleted,
                )
            )
        )
        count = await self.session.scalar(
            select(func.count()).select_from(query.options(noload("*")).subquery())
        )
        result = (
            await self.session.execute(
                statement=query.order_by(Project.updated_at)
                .offset((pagination.page - 1) * pagination.size)
                .limit(pagination.size)
            )
        ).all()

        return PaginatedDbResult(
            count=count or 0,
            rows=[row for row in result],
        )

    async def retrieve_projects_batch(
        self,
        groups: List[str],
        pagination: PageParams,
    ) -> PaginatedDbResult[List[Row[Tuple[Project, VirtualLab]]]]:
        query = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(
                    or_(
                        Project.admin_group_id.in_(groups),
                        Project.member_group_id.in_(groups),
                    ),
                    ~Project.deleted,
                )
            )
        )

        count = await self.session.scalar(
            select(func.count()).select_from(query.options(noload("*")).subquery())
        )

        result = (
            await self.session.execute(
                statement=query.order_by(Project.updated_at)
                .offset((pagination.page - 1) * pagination.size)
                .limit(pagination.size)
            )
        ).all()

        return PaginatedDbResult(
            count=count or 0,
            rows=[row for row in result],
        )

    async def retrieve_one_project_strict(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Tuple[Project, VirtualLab]:
        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(
                    Project.id == project_id,
                    Project.virtual_lab_id == virtual_lab_id,
                )
            )
        )
        result = await self.session.execute(statement=stmt)
        return cast(Tuple[Project, VirtualLab], result.one())

    async def retrieve_one_project(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Tuple[Project, VirtualLab] | None:
        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
        )
        result = (await self.session.execute(statement=stmt)).first()
        return cast(Tuple[Project, VirtualLab] | None, result)

    async def retrieve_one_project_by_id(
        self, project_id: UUID4
    ) -> Tuple[Project, VirtualLab]:
        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(and_(Project.id == project_id))
        )

        result = await self.session.execute(statement=stmt)
        return cast(Tuple[Project, VirtualLab], result.one())

    async def retrieve_one_project_by_name(self, name: str) -> Project | None:
        result = await self.session.scalar(
            select(Project).filter(Project.name == name),
        )
        return cast(
            Project,
            result,
        )

    async def retrieve_project_star(
        self, *, project_id: UUID4, user_id: UUID4
    ) -> ProjectStar | None:
        result = await self.session.scalar(
            select(ProjectStar).filter(
                and_(
                    ProjectStar.project_id == project_id,
                    ProjectStar.user_id == user_id,
                )
            )
        )
        return cast(
            ProjectStar,
            result,
        )

    async def retrieve_starred_projects_per_user(
        self, user_id: UUID4, pagination: PageParams
    ) -> PaginatedDbResult[List[Row[Tuple[ProjectStar, Project]]]]:
        query = (
            select(ProjectStar, Project)
            .join(Project, ProjectStar.project_id == Project.id)
            .filter(
                and_(
                    ~Project.deleted,
                    ProjectStar.user_id == user_id,
                )
            )
        )
        count = await self.session.scalar(
            select(func.count()).select_from(query.options(noload("*")).subquery())
        )

        result = (
            await self.session.execute(
                statement=query.order_by(Project.updated_at)
                .offset((pagination.page - 1) * pagination.size)
                .limit(pagination.size)
            )
        ).all()

        return PaginatedDbResult(
            count=count or 0,
            rows=[row for row in result],
        )

    async def retrieve_project_users_count(self, virtual_lab_id: UUID4) -> int | None:
        result = await self.session.execute(
            select(func.count(Project.id)).where(  # Use select for flexibility
                Project.virtual_lab_id == virtual_lab_id
            )
        )

        return result.scalar()

    async def retrieve_projects_per_lab_count(
        self, virtual_lab_id: UUID4
    ) -> int | None:
        result = await self.session.scalar(
            select(func.count(Project.id)).where(
                and_(~Project.deleted, Project.virtual_lab_id == virtual_lab_id)
            )
        )

        return cast(
            int,
            result,
        )

    async def search(
        self,
        *,
        query_term: str,
        virtual_lab_id: UUID4 | None = None,
        groups_ids: list[str] | None = None,
    ) -> List[Tuple[Project, VirtualLab]]:
        """
        the search fn can be used either for the full list of projects
        or provide list of projects for search within it
        """
        conditions = [
            ~Project.deleted,
            func.lower(Project.name).like(f"%{query_term.lower()}%"),
        ]
        if virtual_lab_id and groups_ids and (len(groups_ids) > 0):
            conditions.append(
                and_(
                    Project.virtual_lab_id == virtual_lab_id,
                    or_(
                        Project.admin_group_id.in_(groups_ids),
                        Project.admin_group_id.in_(groups_ids),
                    ),
                )
            )

        elif groups_ids and (len(groups_ids) > 0):
            conditions.append(
                or_(
                    Project.admin_group_id.in_(groups_ids),
                    Project.admin_group_id.in_(groups_ids),
                ),
            )

        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(*conditions)
            .order_by(Project.updated_at)
        )
        result = (await self.session.execute(statement=stmt)).all()

        return cast(
            List[Tuple[Project, VirtualLab]],
            result,
        )

    async def check_project_exists_by_name(self, *, query_term: str) -> int | None:
        count = await self.session.scalar(
            select(func.count(Project.id)).filter(
                func.lower(Project.name) == func.lower(query_term)
            )
        )
        return cast(
            int,
            count,
        )

    async def check_project_exists_by_name_per_vlab(
        self, *, vlab_id: UUID, query_term: str
    ) -> int | None:
        count = await self.session.scalar(
            select(func.count(Project.id)).filter(
                and_(
                    Project.virtual_lab_id == vlab_id,
                    func.lower(Project.name) == func.lower(query_term),
                )
            )
        )
        return cast(
            int,
            count,
        )

    async def get_owned_projects_count(self, user_id: UUID4) -> int:
        """Count projects where user is the owner"""
        query = select(func.count(Project.id)).where(
            and_(~Project.deleted, Project.owner_id == user_id)
        )
        result = await self.session.scalar(query)
        return result or 0

    async def get_member_projects_count(
        self, user_id: UUID4, group_ids: list[str]
    ) -> int:
        """Count projects where user is a member (but not owner)"""

        query = select(func.count(Project.id)).where(
            and_(
                ~Project.deleted,
                Project.owner_id != user_id,  # Not the owner
                or_(
                    Project.admin_group_id.in_(group_ids),
                    Project.member_group_id.in_(group_ids),
                ),
            )
        )
        result = await self.session.scalar(query)
        return result or 0


class ProjectMutationRepository:
    session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_new_project(
        self,
        *,
        payload: ProjectCreationBody,
        id: UUID4,
        owner_id: UUID4,
        nexus_project_id: str,
        virtual_lab_id: UUID4,
        admin_group_id: str,
        member_group_id: str,
    ) -> Project:
        project = Project(
            id=id,
            name=payload.name,
            description=payload.description,
            nexus_project_id=nexus_project_id,
            virtual_lab_id=virtual_lab_id,
            admin_group_id=admin_group_id,
            member_group_id=member_group_id,
            owner_id=owner_id,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def un_delete_project(
        self, *, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Row[Tuple[UUID, str, str, bool, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(deleted=False, deleted_at=None)
            .returning(
                Project.id,
                Project.admin_group_id,
                Project.member_group_id,
                Project.deleted,
                Project.deleted_at,
            )
        )
        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.one()

    async def delete_project(
        self, virtual_lab_id: UUID4, project_id: UUID4, user_id: UUID4
    ) -> Row[Tuple[UUID, bool, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(deleted=True, deleted_at=func.now(), deleted_by=user_id)
            .returning(
                Project.id,
                Project.deleted,
                Project.deleted_at,
            )
        )
        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.one()

    async def delete_project_strict(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Row[Tuple[UUID, str, str, bool, datetime]]:
        stmt = (
            delete(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .returning(
                Project.id,
                Project.admin_group_id,
                Project.member_group_id,
                Project.deleted,
                Project.deleted_at,
            )
        )
        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.one()

    async def update_project_nexus_id(
        self, virtual_lab_id: UUID4, project_id: UUID4, nexus_id: str
    ) -> Row[Tuple[UUID, str, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(nexus_project_id=nexus_id)
            .returning(Project.id, Project.nexus_project_id, Project.updated_at)
        )
        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.one()

    async def star_project(self, user_id: UUID4, project_id: UUID4) -> ProjectStar:
        project = ProjectStar(
            project_id=project_id,
            user_id=user_id,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def unstar_project(
        self, *, project_id: UUID4, user_id: UUID4
    ) -> Row[Tuple[UUID, datetime]]:
        stmt = (
            delete(ProjectStar)
            .where(
                and_(
                    ProjectStar.project_id == project_id, ProjectStar.user_id == user_id
                )
            )
            .returning(ProjectStar.project_id, ProjectStar.updated_at)
        )
        result = await self.session.execute(statement=stmt)
        await self.session.commit()
        return result.one()

    async def update_project_data(
        self,
        virtual_lab_id: UUID4,
        project_id: UUID4,
        payload: ProjectUpdateBody,
    ) -> Project:
        stmt = (
            update(Project)
            .where(
                and_(
                    Project.id == project_id,
                    Project.virtual_lab_id == virtual_lab_id,
                )
            )
            .values(
                {
                    key: value
                    for key, value in payload.model_dump(exclude_unset=True).items()
                    if value is not None
                }
            )
            .returning(Project)
        )
        await self.session.execute(statement=stmt)
        await self.session.commit()
        return await self.session.get_one(Project, project_id)
