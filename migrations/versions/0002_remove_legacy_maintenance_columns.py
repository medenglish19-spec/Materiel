"""remove legacy maintenance record columns

Revision ID: 0002_remove_legacy_maintenance_columns
Revises: 0001_baseline
"""

from alembic import op
from sqlalchemy import inspect


revision = "0002_remove_legacy_maintenance_columns"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


_LEGACY_COLUMNS = ("updated_at", "meter_reading", "location")


def upgrade() -> None:
    """Remove obsolete MaintenanceRecord columns defensively."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if "maintenance_records" not in inspector.get_table_names():
        return

    existing = {
        column["name"] for column in inspector.get_columns("maintenance_records")
    }
    legacy = [name for name in _LEGACY_COLUMNS if name in existing]

    if not legacy:
        return

    with op.batch_alter_table("maintenance_records") as batch_op:
        for name in legacy:
            batch_op.drop_column(name)


def downgrade() -> None:
    """Obsolete columns are intentionally not recreated."""
    pass
