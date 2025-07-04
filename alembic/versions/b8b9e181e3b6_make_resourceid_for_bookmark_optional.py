"""make resourceid for bookmark optional

Revision ID: b8b9e181e3b6
Revises: 93c9ff52845c
Create Date: 2025-05-06 10:46:51.952634

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8b9e181e3b6"
down_revision: Union[str, None] = "93c9ff52845c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "bookmark", "resource_id", existing_type=sa.VARCHAR(), nullable=True
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "bookmark", "resource_id", existing_type=sa.VARCHAR(), nullable=False
    )
    # ### end Alembic commands ###
