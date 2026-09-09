"""Add tire and battery specifications to equipment models.

Revision ID: 0022_model_tire_battery_specs
Revises: 0021_theoretical_quantity_nullable
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_model_tire_battery_specs"
down_revision = "0021_theoretical_quantity_nullable"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipment_models", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tire_size", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("battery_capacity_ah", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("battery_voltage_v", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("equipment_models", schema=None) as batch_op:
        batch_op.drop_column("battery_voltage_v")
        batch_op.drop_column("battery_capacity_ah")
        batch_op.drop_column("tire_size")
