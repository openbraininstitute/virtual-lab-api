"""make course start/last_drop/end dates required

Backfills existing NULL course dates (defaulting to today / tomorrow / in two
days, preserving ordering when some dates are already set) and makes the three
columns NOT NULL.

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-09-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SET expressions reference the pre-update row values, so a course with no
    # dates ends up with start = now(), last_drop = now() + 1 day,
    # end = now() + 2 days.
    op.execute(
        sa.text(
            """
            UPDATE course
            SET
                start_date = COALESCE(start_date, now()),
                last_drop_date = COALESCE(
                    last_drop_date,
                    COALESCE(start_date, now()) + INTERVAL '1 day'
                ),
                end_date = COALESCE(
                    end_date,
                    COALESCE(
                        last_drop_date,
                        COALESCE(start_date, now()) + INTERVAL '1 day'
                    ) + INTERVAL '1 day'
                )
            WHERE start_date IS NULL
               OR last_drop_date IS NULL
               OR end_date IS NULL
            """
        )
    )

    op.alter_column(
        "course",
        "start_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "course",
        "last_drop_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "course",
        "end_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "course",
        "end_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "course",
        "last_drop_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "course",
        "start_date",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
