"""drop the vestigial project-within-workspace entity

The product pivoted to project = workspace; the old Project / ProjectAgent tables
and the channels.project_id column had no live callers (project_id was always
NULL). Remove them.

Revision ID: 031
Revises: 030
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("channels", "project_id")
    op.drop_index("idx_project_agents_project", table_name="project_agents")
    op.drop_table("project_agents")
    op.drop_index("idx_projects_workspace_status", table_name="projects")
    op.drop_table("projects")


def downgrade():
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=False), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_projects_workspace_status", "projects", ["workspace_id", "status"])
    op.create_table(
        "project_agents",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("working_dir", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "agent_name", name="uq_project_agent"),
    )
    op.create_index("idx_project_agents_project", "project_agents", ["project_id"])
    op.add_column("channels", sa.Column("project_id", UUID(as_uuid=False),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True))
