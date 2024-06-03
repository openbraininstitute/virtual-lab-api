"""Add bookmarks table

Revision ID: ddd049ba8477
Revises: f7446c78a705
Create Date: 2024-06-03 17:39:30.525153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ddd049ba8477"
down_revision: Union[str, None] = "f7446c78a705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "bookmark",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
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
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_bookmark_resource_id"), table_name="bookmark")
    op.drop_index(op.f("ix_bookmark_project_id"), table_name="bookmark")
    op.drop_table("bookmark")
    # ### end Alembic commands ###
