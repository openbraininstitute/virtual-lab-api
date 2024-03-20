from datetime import datetime
from typing import Any, List, Tuple, cast
from uuid import UUID

from pydantic import UUID4
from sqlalchemy import Row, delete, func, or_, select, update
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import and_

from virtual_labs.domain.project import ProjectCreationBody
from virtual_labs.infrastructure.db.models import Project, ProjectStar, VirtualLab


class ProjectQueryRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve_projects_per_vl_batch(
        self, virtual_lab_id: UUID4, groups: List[str]
    ) -> List[Tuple[Project, VirtualLab]]:
        stmt = (
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
            .order_by(Project.updated_at)
        )
        result = self.session.execute(statement=stmt)
        return cast(List[Tuple[Project, VirtualLab]], result.all())

    def retrieve_projects_batch(
        self, groups: List[str]
    ) -> List[Tuple[Project, VirtualLab]]:
        stmt = (
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
            .order_by(Project.updated_at)
        )
        result = self.session.execute(statement=stmt)
        return cast(List[Tuple[Project, VirtualLab]], result.all())

    def retrieve_one_project_strict(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Tuple[Project, VirtualLab]:
        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
        )
        result = self.session.execute(statement=stmt)
        return cast(Tuple[Project, VirtualLab], result.one())

    def retrieve_one_project(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Row[Tuple[Project, VirtualLab]] | None:
        stmt = (
            select(Project, VirtualLab)
            .join(VirtualLab)
            .filter(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
        )
        result = self.session.execute(statement=stmt)
        return result.first()

    def retrieve_one_project_by_id(self, project_id: UUID4) -> Project:
        return self.session.query(Project).where(Project.id == project_id).one()

    def retrieve_one_project_by_name(self, name: str) -> Project | None:
        return self.session.query(Project).filter(Project.name == name).first()

    def retrieve_project_star(
        self, *, project_id: UUID4, user_id: UUID4
    ) -> ProjectStar | None:
        return (
            self.session.query(ProjectStar)
            .filter(
                and_(
                    ProjectStar.project_id == project_id, ProjectStar.user_id == user_id
                )
            )
            .first()
        )

    def retrieve_starred_projects_per_user(
        self, user_id: UUID4
    ) -> List[Row[Tuple[ProjectStar, Project]]]:
        joined_query = (
            self.session.query(ProjectStar, Project)
            .join(Project, ProjectStar.project_id == Project.id)
            .filter(ProjectStar.user_id == user_id)
        )
        user_starred_projects = joined_query.all()
        return user_starred_projects

    def retrieve_project_users_count(self, virtual_lab_id: UUID4) -> int:
        return (
            self.session.query(Project)
            .filter(Project.virtual_lab_id == virtual_lab_id)
            .count()
        )

    def retrieve_projects_per_lab_count(self, virtual_lab_id: UUID4) -> int:
        return (
            self.session.query(Project)
            .filter(and_(~Project.deleted, Project.virtual_lab_id == virtual_lab_id))
            .count()
        )

    def search(
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
        result = self.session.execute(statement=stmt)
        return cast(List[Tuple[Project, VirtualLab]], result.all())

    def check(self, *, query_term: str) -> Query[Project]:
        query = self.session.query(Project).filter(
            func.lower(Project.name) == func.lower(query_term)
        )
        return query


class ProjectMutationRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_new_project(
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
        self.session.commit()
        self.session.refresh(project)
        return project

    def un_delete_project(
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
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()

    def delete_project(
        self, virtual_lab_id: UUID4, project_id: UUID4, user_id: UUID4
    ) -> Row[Tuple[UUID, str, str, bool, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(deleted=True, deleted_at=func.now(), deleted_by=user_id)
            .returning(
                Project.id,
                Project.admin_group_id,
                Project.member_group_id,
                Project.deleted,
                Project.deleted_at,
            )
        )
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()

    def delete_project_strict(
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
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()

    def update_project_budget(
        self, virtual_lab_id: UUID4, project_id: UUID4, value: float
    ) -> Row[Tuple[UUID, Any, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(budget=value)
            .returning(Project.id, Project.budget, Project.updated_at)
        )
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()

    def update_project_nexus_id(
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
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()

    def star_project(self, user_id: UUID4, project_id: UUID4) -> ProjectStar:
        project = ProjectStar(
            project_id=project_id,
            user_id=user_id,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def unstar_project(
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
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()
