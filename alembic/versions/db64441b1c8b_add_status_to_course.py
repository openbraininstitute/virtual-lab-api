"""add_status_to_course

Revision ID: db64441b1c8b
Revises: b873d0dbb15f
Create Date: 2026-06-06 19:38:36.901346

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db64441b1c8b"
down_revision: Union[str, None] = "b873d0dbb15f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    coursestatus = sa.Enum("DRAFT", "ACTIVE", "VOIDED", name="coursestatus")
    coursestatus.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "course",
        sa.Column("status", coursestatus, nullable=False, server_default="DRAFT"),
    )
    op.create_index(op.f("ix_course_status"), "course", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_course_status"), table_name="course")
    op.drop_column("course", "status")
    sa.Enum(name="coursestatus").drop(op.get_bind(), checkfirst=True)
