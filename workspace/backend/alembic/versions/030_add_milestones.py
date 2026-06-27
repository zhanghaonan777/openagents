"""add milestones table (timeline decisions)

Project timeline: a distilled decision/milestone from a discussion thread.

Revision ID: 030
Revises: 029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "milestones",
        sa.Column("id", UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=False),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", UUID(as_uuid=False),
                  sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False, server_default="decision"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("participants", JSONB(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_milestones_workspace_created", "milestones", ["workspace_id", "created_at"])


def downgrade():
    op.drop_index("idx_milestones_workspace_created", table_name="milestones")
    op.drop_table("milestones")
