"""make_enrolment_project_id_not_null

Revision ID: a3f1c8e92d47
Revises: 1e5787d3b6f6
Create Date: 2026-06-11 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f1c8e92d47"
down_revision: Union[str, None] = "1e5787d3b6f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove any orphan enrolments without a project (should not exist in practice)
    op.execute("DELETE FROM course_enrolment WHERE project_id IS NULL")
    op.alter_column(
        "course_enrolment",
        "project_id",
        existing_type=sa.UUID(),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "course_enrolment",
        "project_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
