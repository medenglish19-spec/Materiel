"""Rename the battery model field to capacity without losing existing values."""
from alembic import op
import sqlalchemy as sa


revision = "20261024_battery_capacity"
down_revision = "20261024_maintenance_operation_warning_hours"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("batteries") as batch:
        batch.alter_column(
            "model",
            new_column_name="capacity",
            existing_type=sa.String(80),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("batteries") as batch:
        batch.alter_column(
            "capacity",
            new_column_name="model",
            existing_type=sa.String(80),
            existing_nullable=True,
        )
