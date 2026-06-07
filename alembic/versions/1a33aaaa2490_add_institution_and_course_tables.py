"""add institution and course tables

Revision ID: 1a33aaaa2490
Revises: 80f793ed56d5
Create Date: 2026-06-07 12:30:07.540558

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a33aaaa2490"
down_revision: Union[str, None] = "80f793ed56d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create institution table
    op.create_table(
        "institution",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_institution_name"), "institution", ["name"], unique=True)

    # 2. Seed Open Brain Institute
    op.execute(
        sa.text("""
            INSERT INTO institution (id, name, contact_email, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                'Open Brain Institute',
                'obi-virtual-lab@openbraininstitute.org',
                now(),
                now()
            )
        """)
    )

    # 3. Create course table
    op.create_table(
        "course",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("virtual_lab_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=False),
        sa.Column("template_project_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("last_drop_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "ACTIVE", "VOIDED", name="coursestatus"),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institution.id"]),
        sa.ForeignKeyConstraint(["template_project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["virtual_lab_id"], ["virtual_lab.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_course_institution_id"), "course", ["institution_id"], unique=False
    )
    op.create_index(op.f("ix_course_status"), "course", ["status"], unique=False)
    op.create_index(
        op.f("ix_course_template_project_id"),
        "course",
        ["template_project_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_course_virtual_lab_id"), "course", ["virtual_lab_id"], unique=True
    )

    # 4. Migrate existing virtual labs with course_template_project_id into course table
    op.execute(
        sa.text("""
            INSERT INTO course (id, virtual_lab_id, institution_id, template_project_id, status, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                vl.id,
                (SELECT i.id FROM institution i WHERE i.name = 'Open Brain Institute'),
                vl.course_template_project_id,
                'DRAFT',
                now(),
                now()
            FROM virtual_lab vl
            WHERE vl.course_template_project_id IS NOT NULL
        """)
    )

    # 5. Drop old columns from virtual_lab
    op.drop_column("virtual_lab", "course_template_project_id")
    op.drop_column("virtual_lab", "is_course_initialized")


def downgrade() -> None:
    # 1. Restore columns on virtual_lab
    op.add_column(
        "virtual_lab",
        sa.Column(
            "is_course_initialized",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.add_column(
        "virtual_lab",
        sa.Column(
            "course_template_project_id", sa.UUID(), autoincrement=False, nullable=True
        ),
    )

    # 2. Migrate data back from course table to virtual_lab
    op.execute(
        sa.text("""
            UPDATE virtual_lab
            SET course_template_project_id = c.template_project_id
            FROM course c
            WHERE c.virtual_lab_id = virtual_lab.id
        """)
    )

    # 3. Drop course table and enum
    op.drop_index(op.f("ix_course_virtual_lab_id"), table_name="course")
    op.drop_index(op.f("ix_course_template_project_id"), table_name="course")
    op.drop_index(op.f("ix_course_status"), table_name="course")
    op.drop_index(op.f("ix_course_institution_id"), table_name="course")
    op.drop_table("course")
    sa.Enum(name="coursestatus").drop(op.get_bind(), checkfirst=True)

    # 4. Drop institution table
    op.drop_index(op.f("ix_institution_name"), table_name="institution")
    op.drop_table("institution")
