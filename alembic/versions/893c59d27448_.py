"""empty message

Revision ID: 893c59d27448
Revises: cb69e5f593db, f55c56122d2b
Create Date: 2025-03-18 11:26:06.458189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '893c59d27448'
down_revision: Union[str, None] = ('cb69e5f593db', 'f55c56122d2b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
