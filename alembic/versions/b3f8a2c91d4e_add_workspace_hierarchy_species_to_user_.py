"""add workspace_hierarchy_species to user_preference

Revision ID: b3f8a2c91d4e
Revises: a114577ba18b
Create Date: 2026-01-13 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f8a2c91d4e"
down_revision: Union[str, None] = "a114577ba18b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_preference",
        sa.Column(
            "workspace_hierarchy_species",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preference", "workspace_hierarchy_species")
