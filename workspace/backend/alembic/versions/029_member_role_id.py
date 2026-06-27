"""add role_id to workspace_members

System-wide identity: an agent records the catalog role it was hired from
(e.g. "backend-developer"), linking the live agent back to its role template.

Revision ID: 029
Revises: 028
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workspace_members", sa.Column("role_id", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("workspace_members", "role_id")
