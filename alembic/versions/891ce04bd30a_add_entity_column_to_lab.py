"""Add entity column to lab

Revision ID: 891ce04bd30a
Revises: aa81eeb4dad6
Create Date: 2024-05-02 10:08:57.981605

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "891ce04bd30a"
down_revision: Union[str, None] = "aa81eeb4dad6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column for entity
    op.add_column("virtual_lab", sa.Column("entity", sa.String()))

    # Add default value "EPFL, Switzerland" for all existing labs
    lab_table = sa.table("virtual_lab", sa.column("entity"))
    op.execute(lab_table.update().values({"entity": "EPFL, Switzerland"}))

    # Now make `entity` table non-nullable
    op.alter_column("virtual_lab", "entity", nullable=False)


def downgrade() -> None:
    op.drop_column("virtual_lab", "entity")
