"""add stripeuser model

Revision ID: c537a55bddba
Revises: d5b175b65c30
Create Date: 2025-03-06 17:30:48.633715

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c537a55bddba"
down_revision: Union[str, None] = "d5b175b65c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "stripe_user",
        "stripe_costumer_id",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
    op.add_column(
        "subscription_plan", sa.Column("currency", sa.String(length=3), nullable=False)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("subscription_plan", "currency")
    op.alter_column(
        "stripe_user",
        "stripe_costumer_id",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )
    # ### end Alembic commands ###
