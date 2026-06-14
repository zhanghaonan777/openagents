# -*- coding: utf-8 -*-
"""Add A2A task concurrency control + lease: a2a_tasks.version + a2a_tasks.deadline_at.

Revision ID: 026
Revises: 025
Create Date: 2026-06-14

- `version` — optimistic-lock counter (SQLAlchemy version_id_col). State
  transitions CAS-check + bump it, so a reaper timing out a task and a worker
  completing it can't lost-update each other.
- `deadline_at` — lease deadline. Non-terminal transitions extend it; the
  maintenance reaper times out tasks whose lease expired.

Guarded with existence checks so the migration is idempotent.
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def _has_column(inspector, table, column):
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_column(inspector, "a2a_tasks", "version"):
        op.add_column("a2a_tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    if not _has_column(inspector, "a2a_tasks", "deadline_at"):
        op.add_column("a2a_tasks", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_column(inspector, "a2a_tasks", "deadline_at"):
        op.drop_column("a2a_tasks", "deadline_at")
    if _has_column(inspector, "a2a_tasks", "version"):
        op.drop_column("a2a_tasks", "version")
