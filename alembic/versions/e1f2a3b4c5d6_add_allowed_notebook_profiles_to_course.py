"""add allowed_notebook_profiles to course

Course-wide allowlist of notebook session profile names. Nullable; NULL means
"not restricted" (all profiles offered), so existing courses keep their current
behaviour with no backfill.

Revision ID: e1f2a3b4c5d6
Revises: f1a2b3c4d5e6
Create Date: 2026-11-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course",
        sa.Column("allowed_notebook_profiles", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("course", "allowed_notebook_profiles")
