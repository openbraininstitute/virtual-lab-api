"""add_indexes_for_expire_cron

Revision ID: c4d8e1f23a97
Revises: b7e2a4f19c83
Create Date: 2026-06-12 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8e1f23a97"
down_revision: Union[str, None] = "b7e2a4f19c83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_course_end_date", "course", ["end_date"])
    op.create_index(
        "ix_course_enrolment_is_dropped", "course_enrolment", ["is_dropped"]
    )
    op.create_index("ix_seat_course_id", "seat", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_seat_course_id", table_name="seat")
    op.drop_index("ix_course_enrolment_is_dropped", table_name="course_enrolment")
    op.drop_index("ix_course_end_date", table_name="course")
