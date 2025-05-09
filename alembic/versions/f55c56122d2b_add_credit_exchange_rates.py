"""Add credit exchange rates

Revision ID: f55c56122d2b
Revises: 294486398197
Create Date: 2025-03-14 21:40:29.312394

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f55c56122d2b"
down_revision: Union[str, None] = "294486398197"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "credit_exchange_rate",
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("currency"),
    )
    op.create_index(
        op.f("ix_credit_exchange_rate_currency"),
        "credit_exchange_rate",
        ["currency"],
        unique=False,
    )
    # ### end Alembic commands ###

    # Insert default values
    op.execute(
        """
        INSERT INTO credit_exchange_rate (currency, rate, description)
        VALUES 
            ('chf', 0.05, 'Swiss Franc'),
            ('usd', 0.055, 'US Dollar'),
            ('eur', 0.048, 'Euro')
        """
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_credit_exchange_rate_currency"), table_name="credit_exchange_rate"
    )
    op.drop_table("credit_exchange_rate")
    # ### end Alembic commands ###
