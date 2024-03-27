"""Add email to project invite

Revision ID: ad2e27bf6c24
Revises: 940a65341fd8
Create Date: 2024-03-27 12:06:17.881194

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ad2e27bf6c24"
down_revision: Union[str, None] = "940a65341fd8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_invite", sa.Column("user_email", sa.String(), nullable=False)
    )
    op.alter_column(
        "project_invite", "role", existing_type=sa.VARCHAR(), nullable=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.alter_column("project_invite", "role", existing_type=sa.VARCHAR(), nullable=True)
    op.drop_column("project_invite", "user_email")
    # ### end Alembic commands ###
