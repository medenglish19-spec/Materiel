"""Require explicit approval before a model's plan drives follow-ups.

Revision ID: 20261009_maintenance_plan_approval
Revises: add_received_date_spare_part_items
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_maintenance_plan_approval"
down_revision = "add_received_date_spare_part_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "maintenance_plans",
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_maintenance_plans_is_approved",
        "maintenance_plans",
        ["is_approved"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_plans_is_approved", table_name="maintenance_plans")
    op.drop_column("maintenance_plans", "is_approved")
