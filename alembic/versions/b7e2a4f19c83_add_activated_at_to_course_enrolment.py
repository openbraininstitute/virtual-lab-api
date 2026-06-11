"""add_activated_at_to_course_enrolment

Revision ID: b7e2a4f19c83
Revises: a3f1c8e92d47
Create Date: 2026-06-12 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2a4f19c83"
down_revision: Union[str, None] = "a3f1c8e92d47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course_enrolment",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("course_enrolment", "activated_at")
