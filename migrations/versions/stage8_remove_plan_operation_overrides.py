"""Remove plan-level operation interval overrides.

Revision ID: stage8_remove_plan_operation_overrides
Revises: stage7_operation_first_execution
"""

from alembic import op
import sqlalchemy as sa

revision = "stage8_remove_plan_operation_overrides"
down_revision = "stage7_operation_first_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "maintenance_plan_operations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("maintenance_plan_operations")}
    legacy = {
        "interval_km_override",
        "interval_hours_override",
        "interval_days_override",
    }
    present = columns & legacy
    if not present:
        return

    where = " OR ".join(f"{name} IS NOT NULL" for name in sorted(present))
    count = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM maintenance_plan_operations WHERE {where}")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "لا يمكن إزالة تجاوزات شروط العمليات من الخطة: توجد بيانات مستخدمة في maintenance_plan_operations. "
            "انقل هذه القيم إلى شروط العملية الأصلية قبل تطبيق Stage 8."
        )

    with op.batch_alter_table("maintenance_plan_operations") as batch:
        for name in sorted(present):
            batch.drop_column(name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "maintenance_plan_operations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("maintenance_plan_operations")}
    with op.batch_alter_table("maintenance_plan_operations") as batch:
        if "interval_km_override" not in columns:
            batch.add_column(sa.Column("interval_km_override", sa.Numeric(10, 1), nullable=True))
        if "interval_hours_override" not in columns:
            batch.add_column(sa.Column("interval_hours_override", sa.Numeric(10, 1), nullable=True))
        if "interval_days_override" not in columns:
            batch.add_column(sa.Column("interval_days_override", sa.Integer(), nullable=True))
