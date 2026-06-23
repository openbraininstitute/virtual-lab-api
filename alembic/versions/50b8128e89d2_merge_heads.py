"""merge_heads

Revision ID: 50b8128e89d2
Revises: 96c83d63c85e, e7b2c4a91f36
Create Date: 2026-06-23 12:28:31.979654

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "50b8128e89d2"
down_revision: Union[str, None] = ("96c83d63c85e", "e7b2c4a91f36")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
