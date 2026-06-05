"""add course table

Revision ID: 255e7314d211
Revises: c15c48abebf3
Create Date: 2026-06-05 13:52:53.470210

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.sql import column, table

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "255e7314d211"
down_revision: Union[str, None] = "c15c48abebf3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create institution for OBI
    institution_table = table(
        "institution",
        column("id", sa.UUID),
        column("name", sa.String),
        column("contact_email", sa.String),
        column("created_at", sa.DateTime(timezone=True)),
        column("updated_at", sa.DateTime(timezone=True)),
    )

    obi_id = sa.text("gen_random_uuid()")
    op.execute(
        institution_table.insert().values(
            id=obi_id,
            name="Open Brain Institute",
            contact_email="obi-virtual-lab@openbraininstitute.org",
            created_at=sa.func.now(),
            updated_at=sa.func.now(),
        )
    )

    # 2. Create course table
    op.create_table(
        "course",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("virtual_lab_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("template_project_id", sa.UUID(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("last_drop_date", sa.Date(), nullable=True),
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
    op.create_index(
        op.f("ix_course_template_project_id"),
        "course",
        ["template_project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_course_virtual_lab_id"), "course", ["virtual_lab_id"], unique=True
    )

    # 3. Migrate existing virtual labs with course_template_project_id into course table
    op.execute(
        sa.text("""
            INSERT INTO course (id, virtual_lab_id, institution_id, template_project_id, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                vl.id,
                (SELECT i.id FROM institution i WHERE i.name = 'Open Brain Institute'),
                vl.course_template_project_id,
                now(),
                now()
            FROM virtual_lab vl
            WHERE vl.course_template_project_id IS NOT NULL
        """)
    )

    # 4. Drop old columns from virtual_lab
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

    # 3. Drop course table
    op.drop_index(op.f("ix_course_virtual_lab_id"), table_name="course")
    op.drop_index(op.f("ix_course_template_project_id"), table_name="course")
    op.drop_index(op.f("ix_course_institution_id"), table_name="course")
    op.drop_table("course")

    # 4. Remove OBI institution
    op.execute(sa.text("DELETE FROM institution WHERE name = 'Open Brain Institute'"))
