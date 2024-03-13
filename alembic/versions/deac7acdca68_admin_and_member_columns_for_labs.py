"""Admin and member columns for labs

Revision ID: deac7acdca68
Revises: c3fc70d340af
Create Date: 2024-03-13 14:42:03.017410

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "deac7acdca68"
down_revision: Union[str, None] = "c3fc70d340af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "virtual_lab", sa.Column("admin_group_id", sa.String(), nullable=False)
    )
    op.add_column(
        "virtual_lab", sa.Column("member_group_id", sa.String(), nullable=False)
    )
    op.create_unique_constraint(
        "unique_admin_group_id_for_lab", "virtual_lab", ["admin_group_id"]
    )
    op.create_unique_constraint(
        "unique_member_group_id_for_lab", "virtual_lab", ["member_group_id"]
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_constraint("unique_admin_group_id_for_lab", "virtual_lab", type_="unique")
    op.drop_constraint("unique_member_group_id_for_lab", "virtual_lab", type_="unique")
    op.drop_column("virtual_lab", "member_group_id")
    op.drop_column("virtual_lab", "admin_group_id")
    # ### end Alembic commands ###
