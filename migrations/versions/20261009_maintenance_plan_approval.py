"""Require explicit approval before a model's plan drives follow-ups.

Revision ID: 20261009_maintenance_plan_approval
Revises: 9cff3cadf131, merge_spare_parts_heads_0034_receipt
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_maintenance_plan_approval"
down_revision = ("9cff3cadf131", "merge_spare_parts_heads_0034_receipt")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "maintenance_plans" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("maintenance_plans")}
    if "is_approved" not in columns:
        op.add_column(
            "maintenance_plans",
            sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("maintenance_plans")}
    if "ix_maintenance_plans_is_approved" not in indexes:
        op.create_index(
            "ix_maintenance_plans_is_approved",
            "maintenance_plans",
            ["is_approved"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "maintenance_plans" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("maintenance_plans")}
    if "ix_maintenance_plans_is_approved" in indexes:
        op.drop_index("ix_maintenance_plans_is_approved", table_name="maintenance_plans")
    columns = {column["name"] for column in inspector.get_columns("maintenance_plans")}
    if "is_approved" in columns:
        op.drop_column("maintenance_plans", "is_approved")
