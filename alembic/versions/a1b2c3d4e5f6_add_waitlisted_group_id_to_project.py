"""add waitlisted_group_id to project

Revision ID: a1b2c3d4e5f6
Revises: e7ca4990c359
Create Date: 2026-07-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e7ca4990c359"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column("waitlisted_group_id", sa.String(), nullable=True, unique=True),
    )


def downgrade() -> None:
    op.drop_column("project", "waitlisted_group_id")
