"""Allow maintenance execution records to be operation-first while retaining legacy rule links.

Revision ID: stage7_operation_first_execution
Revises: stage3_maintenance_operations
"""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision = "stage7_operation_first_execution"
down_revision = "stage3_maintenance_operations"
branch_labels = None
depends_on = None

_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "maintenance_records" not in tables:
        return

    columns = {c["name"]: c for c in inspector.get_columns("maintenance_records")}
    if "rule_id" in columns and not columns["rule_id"].get("nullable", True):
        with op.batch_alter_table("maintenance_records", naming_convention=_NAMING) as batch:
            batch.alter_column("rule_id", existing_type=sa.Integer(), nullable=True)

    indexes = {i["name"] for i in inspect(bind).get_indexes("maintenance_records")}
    if "uq_maintenance_record_equipment_operation_date" not in indexes:
        op.create_index(
            "uq_maintenance_record_equipment_operation_date",
            "maintenance_records",
            ["equipment_id", "operation_id", "maintenance_date"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "maintenance_records" not in tables:
        return

    indexes = {i["name"] for i in inspect(bind).get_indexes("maintenance_records")}
    if "uq_maintenance_record_equipment_operation_date" in indexes:
        op.drop_index("uq_maintenance_record_equipment_operation_date", table_name="maintenance_records")

    columns = {c["name"]: c for c in inspect(bind).get_columns("maintenance_records")}
    if "rule_id" in columns and columns["rule_id"].get("nullable", True):
        null_count = bind.execute(
            sa.text("SELECT COUNT(*) FROM maintenance_records WHERE rule_id IS NULL")
        ).scalar_one()
        if null_count:
            raise RuntimeError("لا يمكن التراجع: توجد سجلات صيانة تعتمد على operation_id دون rule_id قديم.")
        with op.batch_alter_table("maintenance_records", naming_convention=_NAMING) as batch:
            batch.alter_column("rule_id", existing_type=sa.Integer(), nullable=False)
