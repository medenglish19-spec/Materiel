"""add fuel records

revision: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_fuel"
down_revision = "0013_batteries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fuel_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fueling_date", sa.Date(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("fuel_type", sa.String(40), nullable=True),
        sa.Column("document_number", sa.String(100), nullable=True),
        sa.Column("station", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_fuel_quantity_positive"),
        sa.CheckConstraint("meter_value >= 0", name="ck_fuel_meter_nonnegative"),
        sa.UniqueConstraint("equipment_id", "sequence_number", name="uq_fuel_equipment_sequence"),
    )
    op.create_index("ix_fuel_records_equipment_id", "fuel_records", ["equipment_id"])
    op.create_index("ix_fuel_records_fueling_date", "fuel_records", ["fueling_date"])


def downgrade():
    op.drop_table("fuel_records")
