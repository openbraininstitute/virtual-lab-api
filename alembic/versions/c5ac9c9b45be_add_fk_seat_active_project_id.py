"""add_fk_seat_active_project_id

Revision ID: c5ac9c9b45be
Revises: 4bebe19540f0
Create Date: 2026-06-09 16:53:13.392723

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5ac9c9b45be"
down_revision: Union[str, None] = "4bebe19540f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_seat_active_project_id", "seat", "project", ["active_project_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_seat_active_project_id", "seat", type_="foreignkey")
