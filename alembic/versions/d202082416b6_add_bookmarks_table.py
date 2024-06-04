"""Add bookmarks table

Revision ID: d202082416b6
Revises: f7446c78a705
Create Date: 2024-06-04 12:06:30.795709

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d202082416b6"
down_revision: Union[str, None] = "f7446c78a705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bookmark",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bookmark_project_id"), "bookmark", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_bookmark_resource_id"), "bookmark", ["resource_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_bookmark_resource_id"), table_name="bookmark")
    op.drop_index(op.f("ix_bookmark_project_id"), table_name="bookmark")
    op.drop_table("bookmark")
