"""Add maintenance plan and operation structure for Stage 2.

This migration adds the new structural layer without changing the existing
maintenance rule/record behavior.
"""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "stage2_maintenance_structure"
down_revision = "e4f7a1c2b9d0"
branch_labels = None
depends_on = None


_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
}


def _tables(bind):
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "maintenance_operation_groups" not in tables:
        op.create_table(
            "maintenance_operation_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("name", name="uq_maintenance_operation_group_name"),
        )

    tables = _tables(bind)
    if "maintenance_plans" not in tables:
        op.create_table(
            "maintenance_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("equipment_model_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("interval_km", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_hours", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_days", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "interval_km IS NULL OR interval_km > 0",
                name="ck_maintenance_plan_interval_km_positive",
            ),
            sa.CheckConstraint(
                "interval_hours IS NULL OR interval_hours > 0",
                name="ck_maintenance_plan_interval_hours_positive",
            ),
            sa.CheckConstraint(
                "interval_days IS NULL OR interval_days > 0",
                name="ck_maintenance_plan_interval_days_positive",
            ),
            sa.ForeignKeyConstraint(
                ["equipment_model_id"],
                ["equipment_models.id"],
                name="fk_maintenance_plans_equipment_model",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_maintenance_plans_equipment_model_id",
            "maintenance_plans",
            ["equipment_model_id"],
            unique=False,
        )

    tables = _tables(bind)
    if "maintenance_plan_operations" not in tables:
        op.create_table(
            "maintenance_plan_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("operation_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("interval_km_override", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_hours_override", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_days_override", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(
                ["plan_id"],
                ["maintenance_plans.id"],
                name="fk_maintenance_plan_operations_plan",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["operation_id"],
                ["maintenance_rules.id"],
                name="fk_maintenance_plan_operations_operation",
                ondelete="RESTRICT",
            ),
            sa.UniqueConstraint(
                "plan_id",
                "operation_id",
                name="uq_maintenance_plan_operation",
            ),
        )
        op.create_index(
            "ix_maintenance_plan_operations_plan_id",
            "maintenance_plan_operations",
            ["plan_id"],
            unique=False,
        )
        op.create_index(
            "ix_maintenance_plan_operations_operation_id",
            "maintenance_plan_operations",
            ["operation_id"],
            unique=False,
        )

    tables = _tables(bind)
    if "maintenance_records" not in tables:
        return

    columns = {c["name"] for c in inspect(bind).get_columns("maintenance_records")}
    indexes = {i["name"] for i in inspect(bind).get_indexes("maintenance_records")}
    fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys("maintenance_records")}

    with op.batch_alter_table(
        "maintenance_records",
        naming_convention=_NAMING,
    ) as batch:
        if "operation_id" not in columns:
            batch.add_column(sa.Column("operation_id", sa.Integer(), nullable=True))
        if "plan_id" not in columns:
            batch.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))

        if "ix_maintenance_records_operation_id" not in indexes:
            batch.create_index(
                "ix_maintenance_records_operation_id",
                ["operation_id"],
                unique=False,
            )
        if "ix_maintenance_records_plan_id" not in indexes:
            batch.create_index(
                "ix_maintenance_records_plan_id",
                ["plan_id"],
                unique=False,
            )

        if "fk_maintenance_records_operation" not in fks:
            batch.create_foreign_key(
                "fk_maintenance_records_operation",
                "maintenance_rules",
                ["operation_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if "fk_maintenance_records_plan" not in fks:
            batch.create_foreign_key(
                "fk_maintenance_records_plan",
                "maintenance_plans",
                ["plan_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "maintenance_records" in tables:
        columns = {c["name"] for c in inspect(bind).get_columns("maintenance_records")}
        indexes = {i["name"] for i in inspect(bind).get_indexes("maintenance_records")}
        fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys("maintenance_records")}

        with op.batch_alter_table(
            "maintenance_records",
            naming_convention=_NAMING,
        ) as batch:
            if "fk_maintenance_records_plan" in fks:
                batch.drop_constraint("fk_maintenance_records_plan", type_="foreignkey")
            if "fk_maintenance_records_operation" in fks:
                batch.drop_constraint("fk_maintenance_records_operation", type_="foreignkey")
            if "ix_maintenance_records_plan_id" in indexes:
                batch.drop_index("ix_maintenance_records_plan_id")
            if "ix_maintenance_records_operation_id" in indexes:
                batch.drop_index("ix_maintenance_records_operation_id")
            if "plan_id" in columns:
                batch.drop_column("plan_id")
            if "operation_id" in columns:
                batch.drop_column("operation_id")

    tables = _tables(bind)
    if "maintenance_plan_operations" in tables:
        op.drop_table("maintenance_plan_operations")

    tables = _tables(bind)
    if "maintenance_plans" in tables:
        op.drop_table("maintenance_plans")

    tables = _tables(bind)
    if "maintenance_operation_groups" in tables:
        op.drop_table("maintenance_operation_groups")
