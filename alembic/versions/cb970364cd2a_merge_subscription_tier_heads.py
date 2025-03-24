"""merge subscription tier heads

Revision ID: cb970364cd2a
Revises: 8dbea06fbbc9, e4cbe1062ba9
Create Date: 2025-03-24 14:38:46.107266

"""

from typing import Sequence, Tuple, Union

# revision identifiers, used by Alembic.
revision: str = "cb970364cd2a"
down_revision: Union[str, None, Tuple[str, str]] = ("8dbea06fbbc9", "e4cbe1062ba9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
