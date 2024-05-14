"""merge e23d19504702 and 56ad6da93b9c

Revision ID: 43f3dc1937d7
Revises: 56ad6da93b9c, e23d19504702
Create Date: 2024-05-14 16:56:38.614503

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "43f3dc1937d7"
down_revision: Union[tuple[str, str], None] = ("56ad6da93b9c", "e23d19504702")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
