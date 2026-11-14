"""Add operating-hour warning thresholds to maintenance operations.

Revision ID: 20261024_maintenance_operation_warning_hours
Revises: 20261023_maintenance_model_scoped_operations
"""
from alembic import op
import sqlalchemy as sa


revision = "20261024_maintenance_operation_warning_hours"
down_revision = "20261023_maintenance_model_scoped_operations"
branch_labels = None
depends_on = None


_TABLES = (
    ("maintenance_operations", "ck_maintenance_operation_warning_hours_nonnegative"),
    ("maintenance_model_operations", "ck_maintenance_model_operation_warning_hours_nonnegative"),
)


def _inspect(table_name):
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    constraints = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints(table_name)
    }
    return columns, constraints


def upgrade():
    for table_name, constraint_name in _TABLES:
        columns, constraints = _inspect(table_name)
        if "warning_hours" not in columns:
            with op.batch_alter_table(table_name) as batch:
                batch.add_column(sa.Column("warning_hours", sa.Numeric(10, 1), nullable=True))
                if constraint_name not in constraints:
                    batch.create_check_constraint(
                        constraint_name,
                        "warning_hours IS NULL OR warning_hours >= 0",
                    )
        elif constraint_name not in constraints:
            with op.batch_alter_table(table_name) as batch:
                batch.create_check_constraint(
                    constraint_name,
                    "warning_hours IS NULL OR warning_hours >= 0",
                )


def downgrade():
    for table_name, constraint_name in reversed(_TABLES):
        columns, constraints = _inspect(table_name)
        if "warning_hours" in columns:
            with op.batch_alter_table(table_name) as batch:
                if constraint_name in constraints:
                    batch.drop_constraint(constraint_name, type_="check")
                batch.drop_column("warning_hours")
