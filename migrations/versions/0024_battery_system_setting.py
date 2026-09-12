"""Add global battery validity setting.

revision: 0024_battery_system_setting
down_revision: 0023_equipment_first_service_date
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_battery_system_setting"
down_revision = "0023_equipment_first_service_date"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "battery_system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("validity_years", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade():
    op.drop_table("battery_system_settings")
