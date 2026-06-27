"""add projects table + channels.project_id

Project mode phase 2: a goal-scoped grouping of threads inside a workspace.

Revision ID: 027
Revises: 026
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_projects_workspace_status", "projects", ["workspace_id", "status"])
    op.add_column(
        "channels",
        sa.Column("project_id", UUID(as_uuid=False),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade():
    op.drop_column("channels", "project_id")
    op.drop_index("idx_projects_workspace_status", table_name="projects")
    op.drop_table("projects")
