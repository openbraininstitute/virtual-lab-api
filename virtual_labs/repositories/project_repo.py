from datetime import datetime
from typing import Any, List, Tuple
from uuid import UUID

from pydantic import UUID4
from sqlalchemy import Row, delete, func, update
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import and_

from ..domain.project import ProjectCreationModel
from ..infrastructure.db.models import Project, ProjectStar


class ProjectQueryRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve_projects_batch(self, virtual_lab_id: UUID4) -> List[Project]:
        data = (
            self.session.query(Project)
            # TODO: for the moment just return everything until will have KC groups
            # .filter(and_(Project.id in projects, Project.virtual_lab_id == virtual_lab_id))
            .filter(~Project.deleted, Project.virtual_lab_id == virtual_lab_id)
            .all()
        )
        return data

    def retrieve_one_project_strict(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Project:
        return (
            self.session.query(Project)
            .filter(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .one()
        )

    def retrieve_one_project(
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Project | None:
        return (
            self.session.query(Project)
            .filter(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .first()
        )

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

    def retrieve_projects_per_lab_count(self, virtual_lab_id: UUID4) -> int:
        return (
            self.session.query(Project)
            .filter(Project.virtual_lab_id == virtual_lab_id)
            .count()
        )

    def retrieve_project_users_count(self, project_id: UUID4) -> None:
        # TODO: this should be moved to user repository since the data will be gathered from the kc instance
        return

    def search(
        self, *, query_term: str, projects_ids: list[UUID4] | None = None
    ) -> Query[Project]:
        """
        the search fn can be used either for the full list of projects
        or provide list of projects for search within it
        """
        conditions = [
            ~Project.deleted,
            func.lower(Project.name).like(f"%{query_term.lower()}%"),
        ]

        if projects_ids and (len(projects_ids) > 0):
            conditions.append(Project.id.in_(projects_ids))

        return self.session.query(Project).filter(*conditions)

    def check(self, *, query_term: str) -> Query[Project]:
        """
        TODO: check the project for deleted projects
        (depends on the discussion on how will handle deletion)
        """
        query = self.session.query(Project).filter(
            ~Project.deleted, func.lower(Project.name) == func.lower(query_term)
        )
        return query


class ProjectMutationRepository:
    session: Session

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_new_project(
        self,
        *,
        payload: ProjectCreationModel,
        id: UUID4,
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
        self, virtual_lab_id: UUID4, project_id: UUID4
    ) -> Row[Tuple[UUID, str, str, bool, datetime]]:
        stmt = (
            update(Project)
            .where(
                and_(Project.id == project_id, Project.virtual_lab_id == virtual_lab_id)
            )
            .values(deleted=True, deleted_at=func.now())
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

    def star_project(self, user_id: UUID4, project_id: UUID4) -> ProjectStar:
        project = ProjectStar(
            project_id=project_id,
            user_id=user_id,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def unstar_project(self, *, project_id: UUID4, user_id: UUID4) -> Row[Tuple[UUID]]:
        stmt = (
            delete(ProjectStar)
            .where(
                and_(
                    ProjectStar.project_id == project_id, ProjectStar.user_id == user_id
                )
            )
            .returning(ProjectStar.project_id)
        )
        result = self.session.execute(statement=stmt)
        self.session.commit()
        return result.one()
