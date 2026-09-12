"""Add first service date to equipment.

Revision ID: 0023_equipment_first_service_date
Revises: 0022_model_tire_battery_specs
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_equipment_first_service_date"
down_revision = "0022_model_tire_battery_specs"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("first_service_date", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("equipment", schema=None) as batch_op:
        batch_op.drop_column("first_service_date")
