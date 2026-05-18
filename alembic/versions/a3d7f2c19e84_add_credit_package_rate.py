"""add credit_package_rate table and migrate from credit_exchange_rate

Revision ID: a3d7f2c19e84
Revises: 80f793ed56d5
Create Date: 2026-05-18 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3d7f2c19e84"
down_revision: Union[str, None] = "80f793ed56d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the new credit_package_rate table
    op.create_table(
        "credit_package_rate",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("min_credits", sa.Integer(), nullable=False),
        sa.Column("max_credits", sa.Integer(), nullable=True),
        sa.Column("rate", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("discount_pct", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("min_credits > 0", name="check_min_credits_positive"),
        sa.CheckConstraint("rate > 0", name="check_rate_positive"),
        sa.CheckConstraint(
            "max_credits IS NULL OR max_credits >= min_credits",
            name="check_valid_credit_range",
        ),
        sa.CheckConstraint(
            "discount_pct >= 0 AND discount_pct <= 100",
            name="check_discount_pct_range",
        ),
    )
    # Partial unique index: no overlapping active ranges for the same currency
    op.create_index(
        "uq_credit_package_rate_currency_min",
        "credit_package_rate",
        ["currency", "min_credits"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )
    op.create_index(
        "ix_credit_package_rate_lookup",
        "credit_package_rate",
        ["currency", "active", "min_credits"],
    )

    # 2. Migrate data from credit_exchange_rate → credit_package_rate
    # Each existing flat rate becomes a catch-all row (min=1, max=NULL, discount=0)
    op.execute(
        """
        INSERT INTO credit_package_rate (currency, min_credits, max_credits, rate, discount_pct, active)
        SELECT currency, 1, NULL, rate, 0, true
        FROM credit_exchange_rate
        """
    )

    # 3. Drop the old table
    op.drop_table("credit_exchange_rate")

    # 4. Add credit_package_rate_id to billing_quote to persist the rate tier applied
    op.add_column(
        "billing_quote",
        sa.Column("discount_pct", sa.Integer(), server_default="0", nullable=True),
    )
    op.add_column(
        "billing_quote",
        sa.Column("credit_package_rate_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_quote_credit_package_rate",
        "billing_quote",
        "credit_package_rate",
        ["credit_package_rate_id"],
        ["id"],
    )


def downgrade() -> None:
    # 1. Remove discount columns from billing_quote
    op.drop_constraint(
        "fk_billing_quote_credit_package_rate", "billing_quote", type_="foreignkey"
    )
    op.drop_column("billing_quote", "credit_package_rate_id")
    op.drop_column("billing_quote", "discount_pct")

    # 2. Recreate credit_exchange_rate
    op.create_table(
        "credit_exchange_rate",
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("currency"),
    )
    op.create_index(
        "ix_credit_exchange_rate_currency",
        "credit_exchange_rate",
        ["currency"],
    )

    # 2. Migrate back: take the base rate (min_credits=1) from each currency
    op.execute(
        """
        INSERT INTO credit_exchange_rate (currency, rate)
        SELECT currency, rate
        FROM credit_package_rate
        WHERE min_credits = 1 AND active = true
        """
    )

    # 3. Drop credit_package_rate
    op.drop_index("ix_credit_package_rate_lookup", table_name="credit_package_rate")
    op.drop_index(
        "uq_credit_package_rate_currency_min", table_name="credit_package_rate"
    )
    op.drop_table("credit_package_rate")
