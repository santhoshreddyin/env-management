"""environments and variables

Revision ID: 0001
Revises:
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_environments_name", "environments", ["name"], unique=True)
    op.create_table(
        "variables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("environment_id", sa.Integer(),
                  sa.ForeignKey("environments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("environment_id", "key", name="uq_env_key"),
    )


def downgrade() -> None:
    op.drop_table("variables")
    op.drop_index("ix_environments_name", table_name="environments")
    op.drop_table("environments")
