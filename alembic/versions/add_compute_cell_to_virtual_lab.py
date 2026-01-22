"""Add compute_cell to virtual_lab

Revision ID: 2f1767c7dfdf
Revises: f7446c78a705
Create Date: 2026-01-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f1767c7dfdf"
down_revision: Union[str, None] = "f7446c78a705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type
    op.execute("CREATE TYPE computecell AS ENUM ('cell-a', 'cell-b')")

    # Add column with default value
    op.add_column(
        "virtual_lab",
        sa.Column(
            "compute_cell",
            sa.Enum("cell-a", "cell-b", name="computecell"),
            nullable=False,
            server_default="cell-a",
        ),
    )


def downgrade() -> None:
    # Drop the column
    op.drop_column("virtual_lab", "compute_cell")

    # Drop the enum type
    op.execute("DROP TYPE computecell")
