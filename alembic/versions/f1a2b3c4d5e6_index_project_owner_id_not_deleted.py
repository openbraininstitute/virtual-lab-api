"""partial index on project.owner_id for live rows

Every project creation counts the caller's live projects (first-project credit
transfer) and the user stats endpoint reads the same count; both filter
`NOT deleted`, so a partial index on the live rows serves them without
indexing soft-deleted history.

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-11-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_project_owner_id_not_deleted",
        "project",
        ["owner_id"],
        unique=False,
        postgresql_where=sa.text("NOT deleted"),
    )


def downgrade() -> None:
    op.drop_index("ix_project_owner_id_not_deleted", table_name="project")
