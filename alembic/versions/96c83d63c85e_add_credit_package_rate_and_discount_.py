"""add credit package rate and discount fields

Revision ID: 96c83d63c85e
Revises: 80f793ed56d5
Create Date: 2026-06-08 11:21:20.898319

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96c83d63c85e"
down_revision: Union[str, None] = "80f793ed56d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
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
    # partial unique index: no overlapping active ranges for the same currency
    op.create_index(
        "uq_credit_package_rate_currency_min",
        "credit_package_rate",
        ["currency", "min_credits"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )

    # migrate data: each existing flat rate becomes a catch-all row
    # (min=1, max=NULL, discount=0). Autogenerate only diffs schema, so this
    # data copy must be written by hand.
    op.execute(
        """
        INSERT INTO credit_package_rate (currency, min_credits, max_credits, rate, discount_pct, active)
        SELECT currency, 1, NULL, rate, 0, true
        FROM credit_exchange_rate
        """
    )

    # drop the old flat-rate table.
    op.drop_index(
        op.f("ix_credit_exchange_rate_currency"), table_name="credit_exchange_rate"
    )
    op.drop_table("credit_exchange_rate")

    # persist the applied rate tier + discount + quoted credit count on the
    # quote so standalone fulfillment grants exactly what was quoted.
    op.add_column(
        "billing_quote", sa.Column("discount_pct", sa.Integer(), nullable=True)
    )
    op.add_column(
        "billing_quote", sa.Column("credit_package_rate_id", sa.UUID(), nullable=True)
    )
    op.add_column("billing_quote", sa.Column("credits", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_billing_quote_credit_package_rate",
        "billing_quote",
        "credit_package_rate",
        ["credit_package_rate_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_billing_quote_credit_package_rate", "billing_quote", type_="foreignkey"
    )
    op.drop_column("billing_quote", "credits")
    op.drop_column("billing_quote", "credit_package_rate_id")
    op.drop_column("billing_quote", "discount_pct")

    op.create_table(
        "credit_exchange_rate",
        sa.Column("currency", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "rate",
            sa.NUMERIC(precision=10, scale=6),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("description", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint("currency", name=op.f("credit_exchange_rate_pkey")),
    )
    op.create_index(
        op.f("ix_credit_exchange_rate_currency"),
        "credit_exchange_rate",
        ["currency"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO credit_exchange_rate (currency, rate)
        SELECT currency, rate
        FROM credit_package_rate
        WHERE min_credits = 1 AND active = true
        """
    )

    op.drop_index(
        "uq_credit_package_rate_currency_min",
        table_name="credit_package_rate",
        postgresql_where=sa.text("active = true"),
    )
    op.drop_table("credit_package_rate")
