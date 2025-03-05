"""merge subscription_plans and remove_budget_and_plan

Revision ID: d5b175b65c30
Revises: 1849f8159098, ac787ad90af8
Create Date: 2025-03-06 07:29:38.855563

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "d5b175b65c30"
down_revision: Union[str, None] = ("1849f8159098", "ac787ad90af8")  # type: ignore
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
