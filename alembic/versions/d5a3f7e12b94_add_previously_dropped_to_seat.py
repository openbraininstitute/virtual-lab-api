"""add_previously_dropped_to_seat

Revision ID: d5a3f7e12b94
Revises: c4d8e1f23a97
Create Date: 2026-06-12 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5a3f7e12b94"
down_revision: Union[str, None] = "c4d8e1f23a97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "seat",
        sa.Column(
            "previously_dropped",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("seat", "previously_dropped")
