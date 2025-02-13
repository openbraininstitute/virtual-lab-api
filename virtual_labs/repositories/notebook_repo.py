from uuid import UUID

from sqlalchemy import delete, desc, insert, select
from sqlalchemy.sql import Delete, Insert
from sqlalchemy.sql.selectable import Select

from virtual_labs.domain.notebooks import NotebookBulkCreate, NotebookCreate
from virtual_labs.infrastructure.db.models import Notebook


def create_notebook(
    notebook_create: NotebookCreate,
    project_id: UUID,
) -> Notebook:
    return Notebook(**notebook_create.model_dump(), project_id=project_id)


def bulk_create_notebook(
    notebook_create: NotebookBulkCreate,
    project_id: UUID,
) -> Insert:
    data = [
        {**n.model_dump(), "project_id": project_id} for n in notebook_create.notebooks
    ]

    return insert(Notebook).values(data).returning(Notebook)


def get_notebooks(project_id: UUID) -> Select[tuple[Notebook]]:
    return (
        select(Notebook)
        .where(Notebook.project_id == project_id)
        .order_by(desc(Notebook.created_at))
    )


def delete_notebook(id: UUID, project_id: UUID) -> Delete:
    return delete(Notebook).filter_by(id=id, project_id=project_id)
