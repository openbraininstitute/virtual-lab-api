"""merge_heads_compute_cell_and_workspace_hierarchy

Revision ID: 2192a5aa8ba6
Revises: 2f1767c7dfdf, b3f8a2c91d4e
Create Date: 2026-01-22 19:33:58.183748

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "2192a5aa8ba6"
down_revision: Union[str, Sequence[str], None] = ("2f1767c7dfdf", "b3f8a2c91d4e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
