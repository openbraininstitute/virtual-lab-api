"""normalize billing tax enums

Revision ID: a4a8f62f7d24
Revises: 91f3e0f0b8f7
Create Date: 2026-05-05 21:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4a8f62f7d24"
down_revision: Union[str, None] = "91f3e0f0b8f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

billing_flow_enum = postgresql.ENUM(
    "STANDALONE",
    "SUBSCRIPTION",
    name="billingflow",
)
tax_behavior_enum = postgresql.ENUM("EXCLUSIVE", name="taxbehavior")
tax_status_enum = postgresql.ENUM(
    "CALCULATED",
    "NOT_APPLICABLE",
    "PENDING",
    "FAILED",
    name="taxstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    billing_flow_enum.create(bind, checkfirst=True)
    tax_behavior_enum.create(bind, checkfirst=True)
    tax_status_enum.create(bind, checkfirst=True)

    op.alter_column(
        "billing_quote",
        "flow",
        existing_type=sa.String(length=50),
        type_=billing_flow_enum,
        postgresql_using="upper(flow)::billingflow",
        existing_nullable=False,
    )
    op.alter_column(
        "billing_quote",
        "tax_behavior",
        existing_type=sa.String(length=50),
        type_=tax_behavior_enum,
        postgresql_using="upper(tax_behavior)::taxbehavior",
        existing_nullable=False,
    )
    op.alter_column(
        "billing_quote",
        "tax_status",
        existing_type=sa.String(length=50),
        type_=tax_status_enum,
        postgresql_using="upper(tax_status)::taxstatus",
        existing_nullable=False,
    )
    op.alter_column(
        "subscription_payment",
        "tax_behavior",
        existing_type=sa.String(length=50),
        type_=tax_behavior_enum,
        postgresql_using=(
            "case when tax_behavior is null then null "
            "else upper(tax_behavior)::taxbehavior end"
        ),
        existing_nullable=True,
    )
    op.alter_column(
        "subscription_payment",
        "tax_status",
        existing_type=sa.String(length=50),
        type_=tax_status_enum,
        postgresql_using=(
            "case when tax_status is null then null "
            "else upper(tax_status)::taxstatus end"
        ),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "subscription_payment",
        "tax_status",
        existing_type=tax_status_enum,
        type_=sa.String(length=50),
        postgresql_using="lower(tax_status::text)",
        existing_nullable=True,
    )
    op.alter_column(
        "subscription_payment",
        "tax_behavior",
        existing_type=tax_behavior_enum,
        type_=sa.String(length=50),
        postgresql_using="lower(tax_behavior::text)",
        existing_nullable=True,
    )
    op.alter_column(
        "billing_quote",
        "tax_status",
        existing_type=tax_status_enum,
        type_=sa.String(length=50),
        postgresql_using="lower(tax_status::text)",
        existing_nullable=False,
    )
    op.alter_column(
        "billing_quote",
        "tax_behavior",
        existing_type=tax_behavior_enum,
        type_=sa.String(length=50),
        postgresql_using="lower(tax_behavior::text)",
        existing_nullable=False,
    )
    op.alter_column(
        "billing_quote",
        "flow",
        existing_type=billing_flow_enum,
        type_=sa.String(length=50),
        postgresql_using="lower(flow::text)",
        existing_nullable=False,
    )

    bind = op.get_bind()
    tax_status_enum.drop(bind, checkfirst=True)
    tax_behavior_enum.drop(bind, checkfirst=True)
    billing_flow_enum.drop(bind, checkfirst=True)
