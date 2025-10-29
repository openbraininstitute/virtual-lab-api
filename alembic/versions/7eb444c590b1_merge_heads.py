"""merge_heads

Revision ID: 7eb444c590b1
Revises: 2dd76784caea, b8b9e181e3b6
Create Date: 2025-05-22 21:06:03.060019

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "7eb444c590b1"
down_revision: Union[str, Sequence[str], None] = ("2dd76784caea", "b8b9e181e3b6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
