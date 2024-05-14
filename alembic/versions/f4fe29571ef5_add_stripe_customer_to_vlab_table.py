"""add stripe customer to vlab table

Revision ID: f4fe29571ef5
Revises: 6338b6ac5353
Create Date: 2024-05-06 16:15:25.835704

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.orm import Session

from alembic import op
from virtual_labs.infrastructure.db.models import VirtualLab
from virtual_labs.infrastructure.stripe.config import stripe_client

# revision identifiers, used by Alembic.
revision: str = "f4fe29571ef5"
down_revision: Union[str, None] = "6338b6ac5353"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    session = Session(bind=conn)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("payment_method", "customerId")
    op.add_column(
        "virtual_lab", sa.Column("stripe_customer_id", sa.String(), nullable=True)
    )
    for item in session.query(VirtualLab.id):
        session.execute(
            statement=sa.update(VirtualLab)
            .where(VirtualLab.id == item.id)
            .values(stripe_customer_id=stripe_client.customers.create().id)
        )
    session.commit()
    op.alter_column(
        table_name="virtual_lab", column_name="stripe_customer_id", nullable=False
    )
    op.create_unique_constraint(
        "virtual_lab_stripe_customer_id_unique", "virtual_lab", ["stripe_customer_id"]
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("virtual_lab", "stripe_customer_id")
    op.add_column(
        "payment_method",
        sa.Column("customerId", sa.VARCHAR(), autoincrement=False, nullable=False),
    )
    # ### end Alembic commands ###
