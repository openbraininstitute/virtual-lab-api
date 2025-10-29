"""Initialize db

Revision ID: 49016d5a3d53
Revises:
Create Date: 2024-03-11 14:02:14.137553

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from virtual_labs.infrastructure.plans_data import plans_data

# revision identifiers, used by Alembic.
revision: str = "49016d5a3d53"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    plan_table = op.create_table(
        "plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(plan_table.insert().values(plans_data))

    op.create_index(op.f("ix_plan_name"), "plan", ["name"], unique=True)
    op.create_table(
        "virtual_lab",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nexus_organization_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference_email", sa.String(length=255), nullable=True),
        sa.Column("budget", sa.Float(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plan.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nexus_organization_id"),
    )
    op.create_index(
        op.f("ix_virtual_lab_deleted"), "virtual_lab", ["deleted"], unique=False
    )
    op.create_index(op.f("ix_virtual_lab_name"), "virtual_lab", ["name"], unique=False)
    op.create_index(
        "unique_lab_name_for_non_deleted",
        "virtual_lab",
        ["name", "deleted"],
        unique=True,
        postgresql_where=sa.text("NOT deleted"),
    )
    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nexus_project_id", sa.String(), nullable=False),
        sa.Column("kc_project_group_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=True),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("virtual_lab_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["virtual_lab_id"],
            ["virtual_lab.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kc_project_group_id"),
        sa.UniqueConstraint("nexus_project_id"),
    )
    op.create_index(op.f("ix_project_name"), "project", ["name"], unique=False)
    op.create_index(
        "unique_name_for_non_deleted",
        "project",
        ["name", "deleted"],
        unique=True,
        postgresql_where=sa.text("NOT deleted"),
    )
    op.create_table(
        "virtual_lab_invite",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("inviter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("virtual_lab_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["virtual_lab_id"],
            ["virtual_lab.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_invite",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("inviter_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_star",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("project_star")
    op.drop_table("project_invite")
    op.drop_table("virtual_lab_invite")
    op.drop_index(
        "unique_name_for_non_deleted",
        table_name="project",
        postgresql_where=sa.text("NOT deleted"),
    )
    op.drop_index(op.f("ix_project_name"), table_name="project")
    op.drop_table("project")
    op.drop_index(
        "unique_lab_name_for_non_deleted",
        table_name="virtual_lab",
        postgresql_where=sa.text("NOT deleted"),
    )
    op.drop_index(op.f("ix_virtual_lab_name"), table_name="virtual_lab")
    op.drop_index(op.f("ix_virtual_lab_deleted"), table_name="virtual_lab")
    op.drop_table("virtual_lab")
    op.drop_index(op.f("ix_plan_name"), table_name="plan")
    op.drop_table("plan")
    # ### end Alembic commands ###
