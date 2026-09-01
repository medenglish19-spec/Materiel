"""add tire management module

revision: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_tires"
down_revision = "0011_fault_exploitation_impact"
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
        "tires",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("serial_number", sa.String(80), nullable=False),
        sa.Column("brand", sa.String(80), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("size", sa.String(50), nullable=True),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("acquisition_document", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("serial_number", name="uq_tires_serial_number"),
    )
    op.create_index("ix_tires_serial_number", "tires", ["serial_number"])
    op.create_index("ix_tires_expiry_date", "tires", ["expiry_date"])

    op.create_table(
        "tire_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(250), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_tire_positions_code"),
    )
    op.create_index("ix_tire_positions_code", "tire_positions", ["code"])

    op.create_table(
        "tire_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tire_id", sa.Integer(), sa.ForeignKey("tires.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("tire_positions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=True),
        sa.Column("document_number", sa.String(100), nullable=True),
        sa.Column("reason", sa.String(250), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("movement_type IN ('install', 'move', 'remove')", name="ck_tire_movement_type"),
    )
    op.create_index("ix_tire_movements_tire_id", "tire_movements", ["tire_id"])
    op.create_index("ix_tire_movements_movement_date", "tire_movements", ["movement_date"])
    op.create_index("ix_tire_movements_equipment_id", "tire_movements", ["equipment_id"])


def downgrade():
    op.drop_table("tire_movements")
    op.drop_table("tire_positions")
    op.drop_index("ix_tires_expiry_date", table_name="tires")
    op.drop_index("ix_tires_serial_number", table_name="tires")
    op.drop_table("tires")
