"""add_course_enrolment_table

Revision ID: 54b047e16a93
Revises: ae20bcced8c2
Create Date: 2026-06-10 19:51:55.748829

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "54b047e16a93"
down_revision: Union[str, None] = "ae20bcced8c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create course_enrolment table
    op.create_table(
        "course_enrolment",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("student_id", sa.String(length=255), nullable=False),
        sa.Column("claimed_by", sa.UUID(), nullable=True),
        sa.Column("is_dropped", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id", "contact_email", name="uq_enrolment_course_email"
        ),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_course_enrolment_claimed_by"),
        "course_enrolment",
        ["claimed_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_enrolment_course_id"),
        "course_enrolment",
        ["course_id"],
        unique=False,
    )

    # 2. Data migration: create enrolment records for existing assigned seats
    op.execute(
        """
        INSERT INTO course_enrolment (course_id, project_id, contact_email, student_id, claimed_by, is_dropped, created_at)
        SELECT
            s.course_id,
            s.active_project_id,
            COALESCE(p.contact_email, ''),
            p.name,
            p.owner_id,
            p.is_dropped,
            COALESCE(s.created_at, now())
        FROM seat s
        JOIN project p ON s.active_project_id = p.id
        WHERE s.active_project_id IS NOT NULL
        """
    )

    # 3. Add enrolment_id to seat
    op.add_column("seat", sa.Column("enrolment_id", sa.UUID(), nullable=True))

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

    # 5. Drop old constraints and column from seat
    op.drop_constraint("seat_active_project_id_key", "seat", type_="unique")
    op.drop_constraint("fk_seat_active_project_id", "seat", type_="foreignkey")
    op.drop_column("seat", "active_project_id")

    # 6. Add new constraints on enrolment_id
    op.create_unique_constraint("seat_enrolment_id_key", "seat", ["enrolment_id"])
    op.create_foreign_key(
        "seat_enrolment_id_fkey", "seat", "course_enrolment", ["enrolment_id"], ["id"]
    )

    # 7. Drop contact_email and is_dropped from project
    op.drop_column("project", "contact_email")
    op.drop_column("project", "is_dropped")


def downgrade() -> None:
    # Re-add project columns
    op.add_column(
        "project",
        sa.Column(
            "contact_email", sa.VARCHAR(length=255), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "project",
        sa.Column(
            "is_dropped",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
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
        sa.Column("active_project_id", sa.UUID(), autoincrement=False, nullable=True),
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

    # Restore old constraints
    op.create_foreign_key(
        "fk_seat_active_project_id", "seat", "project", ["active_project_id"], ["id"]
    )
    op.create_unique_constraint(
        "seat_active_project_id_key", "seat", ["active_project_id"]
    )

    # Drop new column and constraints
    op.drop_constraint("seat_enrolment_id_fkey", "seat", type_="foreignkey")
    op.drop_constraint("seat_enrolment_id_key", "seat", type_="unique")
    op.drop_column("seat", "enrolment_id")

    # Drop course_enrolment table
    op.drop_index(op.f("ix_course_enrolment_course_id"), table_name="course_enrolment")
    op.drop_index(op.f("ix_course_enrolment_claimed_by"), table_name="course_enrolment")
    op.drop_table("course_enrolment")
