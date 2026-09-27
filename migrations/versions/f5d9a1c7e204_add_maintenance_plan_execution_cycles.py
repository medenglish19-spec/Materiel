"""Add independent maintenance plan execution cycles.

Revision ID: f5d9a1c7e204
Revises: f4c8e2a91b7d
"""

from alembic import op
import sqlalchemy as sa


revision = "f5d9a1c7e204"
down_revision = "f4c8e2a91b7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_plan_executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("execution_date", sa.Date(), nullable=False),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=True),
        sa.Column("work_order", sa.String(80), nullable=True),
        sa.Column("workshop", sa.String(120), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["maintenance_plans.id"], name="fk_maintenance_plan_executions_plan", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], name="fk_maintenance_plan_executions_equipment", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_maintenance_plan_executions_created_by", ondelete="SET NULL"),
    )
    op.create_index(
        "ix_maintenance_plan_execution_equipment_date",
        "maintenance_plan_executions",
        ["equipment_id", "execution_date"],
    )
    op.create_index(
        "ix_maintenance_plan_executions_plan_id",
        "maintenance_plan_executions",
        ["plan_id"],
    )
    op.create_index(
        "ix_maintenance_plan_executions_equipment_id",
        "maintenance_plan_executions",
        ["equipment_id"],
    )
    op.create_index(
        "ix_maintenance_plan_executions_execution_date",
        "maintenance_plan_executions",
        ["execution_date"],
    )
    op.create_index(
        "ix_maintenance_plan_executions_created_by_id",
        "maintenance_plan_executions",
        ["created_by_id"],
    )

    op.create_table(
        "maintenance_plan_execution_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("maintenance_record_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["maintenance_plan_executions.id"],
            name="fk_maintenance_plan_execution_operations_execution",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["maintenance_operations.id"],
            name="fk_maintenance_plan_execution_operations_operation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["maintenance_record_id"],
            ["maintenance_records.id"],
            name="fk_maintenance_plan_execution_operations_record",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "execution_id",
            "operation_id",
            name="uq_maintenance_plan_execution_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'skipped')",
            name="ck_maintenance_plan_execution_operation_status",
        ),
    )
    op.create_index(
        "ix_maintenance_plan_execution_operations_execution_id",
        "maintenance_plan_execution_operations",
        ["execution_id"],
    )
    op.create_index(
        "ix_maintenance_plan_execution_operations_operation_id",
        "maintenance_plan_execution_operations",
        ["operation_id"],
    )
    op.create_index(
        "ix_maintenance_plan_execution_operations_maintenance_record_id",
        "maintenance_plan_execution_operations",
        ["maintenance_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_plan_execution_operations_maintenance_record_id",
        table_name="maintenance_plan_execution_operations",
    )
    op.drop_index(
        "ix_maintenance_plan_execution_operations_operation_id",
        table_name="maintenance_plan_execution_operations",
    )
    op.drop_index(
        "ix_maintenance_plan_execution_operations_execution_id",
        table_name="maintenance_plan_execution_operations",
    )
    op.drop_table("maintenance_plan_execution_operations")

    op.drop_index(
        "ix_maintenance_plan_executions_created_by_id",
        table_name="maintenance_plan_executions",
    )
    op.drop_index(
        "ix_maintenance_plan_executions_execution_date",
        table_name="maintenance_plan_executions",
    )
    op.drop_index(
        "ix_maintenance_plan_executions_equipment_id",
        table_name="maintenance_plan_executions",
    )
    op.drop_index(
        "ix_maintenance_plan_executions_plan_id",
        table_name="maintenance_plan_executions",
    )
    op.drop_index(
        "ix_maintenance_plan_execution_equipment_date",
        table_name="maintenance_plan_executions",
    )
    op.drop_table("maintenance_plan_executions")
