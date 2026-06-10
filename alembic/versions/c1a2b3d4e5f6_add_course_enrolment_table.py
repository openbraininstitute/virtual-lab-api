"""add_course_enrolment_table

Revision ID: c1a2b3d4e5f6
Revises: ae20bcced8c2
Create Date: 2025-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "ae20bcced8c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create course_enrolment table
    op.create_table(
        "course_enrolment",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("student_id", sa.String(255), nullable=False),
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_dropped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_course_enrolment_course_id", "course_enrolment", ["course_id"])
    op.create_index(
        "ix_course_enrolment_claimed_by", "course_enrolment", ["claimed_by"]
    )
    op.create_unique_constraint(
        "uq_enrolment_course_email",
        "course_enrolment",
        ["course_id", "contact_email"],
    )

    # 2. Data migration: create enrolment records for existing assigned seats
    op.execute(
        """
        INSERT INTO course_enrolment (id, course_id, project_id, contact_email, student_id, claimed_by, is_dropped, created_at)
        SELECT
            gen_random_uuid(),
            s.course_id,
            s.active_project_id,
            COALESCE(p.contact_email, ''),
            p.name,
            p.owner_id,
            p.is_dropped,
            s.created_at
        FROM seat s
        JOIN project p ON s.active_project_id = p.id
        WHERE s.active_project_id IS NOT NULL
        """
    )

    # 3. Add enrolment_id column to seat
    op.add_column(
        "seat",
        sa.Column("enrolment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 4. Populate enrolment_id from migrated data
    op.execute(
        """
        UPDATE seat s
        SET enrolment_id = ce.id
        FROM course_enrolment ce
        WHERE ce.project_id = s.active_project_id
          AND s.active_project_id IS NOT NULL
        """
    )

    # 5. Drop old FK constraint and column
    op.drop_constraint("seat_active_project_id_fkey", "seat", type_="foreignkey")
    op.drop_constraint("seat_active_project_id_key", "seat", type_="unique")
    op.drop_column("seat", "active_project_id")

    # 6. Add FK + unique constraint on new column
    op.create_foreign_key(
        "seat_enrolment_id_fkey",
        "seat",
        "course_enrolment",
        ["enrolment_id"],
        ["id"],
    )
    op.create_unique_constraint("seat_enrolment_id_key", "seat", ["enrolment_id"])

    # 7. Drop contact_email and is_dropped from project (now on course_enrolment)
    op.drop_column("project", "contact_email")
    op.drop_column("project", "is_dropped")


def downgrade() -> None:
    # Re-add project columns
    op.add_column("project", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column(
        "project",
        sa.Column("is_dropped", sa.Boolean(), server_default="false", nullable=False),
    )

    # Restore project columns from enrolment data
    op.execute(
        """
        UPDATE project p
        SET contact_email = ce.contact_email,
            is_dropped = ce.is_dropped
        FROM course_enrolment ce
        WHERE ce.project_id = p.id
        """
    )

    # Re-add active_project_id to seat
    op.add_column(
        "seat",
        sa.Column("active_project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Populate from enrolment
    op.execute(
        """
        UPDATE seat s
        SET active_project_id = ce.project_id
        FROM course_enrolment ce
        WHERE ce.id = s.enrolment_id
        """
    )

    # Restore old FK and unique constraint
    op.create_foreign_key(
        "seat_active_project_id_fkey",
        "seat",
        "project",
        ["active_project_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "seat_active_project_id_key", "seat", ["active_project_id"]
    )

    # Drop new column and constraints
    op.drop_constraint("seat_enrolment_id_fkey", "seat", type_="foreignkey")
    op.drop_constraint("seat_enrolment_id_key", "seat", type_="unique")
    op.drop_column("seat", "enrolment_id")

    # Drop course_enrolment table
    op.drop_table("course_enrolment")
