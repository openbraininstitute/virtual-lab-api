"""add_budget_depleted_to_course

Revision ID: e7b2c4a91f36
Revises: d5a3f7e12b94
Create Date: 2026-06-12 16:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b2c4a91f36"
down_revision: Union[str, None] = "d5a3f7e12b94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "course",
        sa.Column(
            "budget_depleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("course", "budget_depleted")
