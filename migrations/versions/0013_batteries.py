"""add battery management module

revision: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_batteries"
down_revision = "0012_tires"
branch_labels = None
depends_on = None


def _audit_columns():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def upgrade():
    op.create_table(
        "batteries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("serial_number", sa.String(80), nullable=False),
        sa.Column("brand", sa.String(80), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("acquisition_document", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("serial_number", name="uq_batteries_serial_number"),
    )
    op.create_index("ix_batteries_serial_number", "batteries", ["serial_number"])
    op.create_index("ix_batteries_expiry_date", "batteries", ["expiry_date"])

    op.create_table(
        "battery_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("battery_id", sa.Integer(), sa.ForeignKey("batteries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=True),
        sa.Column("document_number", sa.String(100), nullable=True),
        sa.Column("reason", sa.String(250), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("movement_type IN ('install', 'move', 'remove')", name="ck_battery_movement_type"),
    )
    op.create_index("ix_battery_movements_battery_id", "battery_movements", ["battery_id"])
    op.create_index("ix_battery_movements_movement_date", "battery_movements", ["movement_date"])
    op.create_index("ix_battery_movements_equipment_id", "battery_movements", ["equipment_id"])


def downgrade():
    op.drop_table("battery_movements")
    op.drop_index("ix_batteries_expiry_date", table_name="batteries")
    op.drop_index("ix_batteries_serial_number", table_name="batteries")
    op.drop_table("batteries")
