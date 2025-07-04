"""Rename BookmarkCategory ExperimentsBoutonDensity to ExperimentalBoutonDensity

Revision ID: 93c9ff52845c
Revises: b21a2d089147
Create Date: 2025-04-12 19:00:44.214263

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93c9ff52845c"
down_revision: Union[str, None] = "b21a2d089147"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute(
        "ALTER TYPE bookmarkcategory RENAME VALUE 'ExperimentsBoutonDensity' TO 'ExperimentalBoutonDensity'"
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.execute(
        "ALTER TYPE bookmarkcategory RENAME VALUE 'ExperimentalBoutonDensity' TO 'ExperimentsBoutonDensity'"
    )
    # ### end Alembic commands ###
