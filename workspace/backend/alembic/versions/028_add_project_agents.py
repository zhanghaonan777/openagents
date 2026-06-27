"""add project_agents table

Project mode phase 3: a role recruited into a project (the project's own team).

Revision ID: 028
Revises: 027
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_agents",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=False),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Text(), nullable=True),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("working_dir", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "agent_name", name="uq_project_agent"),
    )
    op.create_index("idx_project_agents_project", "project_agents", ["project_id"])


def downgrade():
    op.drop_index("idx_project_agents_project", table_name="project_agents")
    op.drop_table("project_agents")
