# -*- coding: utf-8 -*-
"""Add A2A task delegation: a2a_tasks table + workspace_members.task_skills.

Revision ID: 025
Revises: 024
Create Date: 2026-06-14

Introduces protocol-level (Agent2Agent) structured delegation on top of the
ONM event bus:

  - `a2a_tasks` — the A2A Task object (id / contextId / status / history /
    artifacts) modelling a point-to-point delegation (delegator → contractor)
    with the A2A TaskState lifecycle.
  - `workspace_members.task_skills` — A2A AgentSkill[] an agent advertises for
    capability discovery (Agent Card assembly).

Guarded with existence checks so the migration is idempotent.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "workspace_members", "task_skills"):
        op.add_column("workspace_members", sa.Column("task_skills", JSONB(), nullable=True))

    if not _has_table(inspector, "a2a_tasks"):
        op.create_table(
            "a2a_tasks",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("workspace_id", UUID(as_uuid=False),
                      sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("context_id", sa.Text(), nullable=True),
            sa.Column("delegator", sa.Text(), nullable=False),
            sa.Column("contractor", sa.Text(), nullable=False),
            sa.Column("skill_id", sa.Text(), nullable=True),
            sa.Column("state", sa.Text(), nullable=False, server_default="submitted"),
            sa.Column("input", JSONB(), nullable=True),
            sa.Column("artifacts", JSONB(), nullable=True),
            sa.Column("history", JSONB(), nullable=True),
            sa.Column("metadata", JSONB(), nullable=True),
            sa.Column("channel_name", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("idx_a2a_tasks_ws_contractor_state", "a2a_tasks",
                        ["workspace_id", "contractor", "state"])
        op.create_index("idx_a2a_tasks_ws_context", "a2a_tasks",
                        ["workspace_id", "context_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "a2a_tasks"):
        op.drop_index("idx_a2a_tasks_ws_context", table_name="a2a_tasks")
        op.drop_index("idx_a2a_tasks_ws_contractor_state", table_name="a2a_tasks")
        op.drop_table("a2a_tasks")

    if _has_column(inspector, "workspace_members", "task_skills"):
        op.drop_column("workspace_members", "task_skills")
