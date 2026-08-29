"""create faults, repairs, and spare-parts tables

revision: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_faults_repairs"
down_revision = "0006_model_theoretical_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faults",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("maintenance_record_id", sa.Integer(), nullable=True),
        sa.Column("reported_date", sa.Date(), nullable=False),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=True),
        sa.Column("fault_type", sa.String(80), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["maintenance_record_id"], ["maintenance_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_fault_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'diagnosing', 'repairing', 'waiting_parts', 'repaired', 'closed')",
            name="ck_fault_status",
        ),
        sa.CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="ck_fault_meter_nonnegative",
        ),
    )
    op.create_index("ix_faults_id", "faults", ["id"])
    op.create_index("ix_faults_equipment_id", "faults", ["equipment_id"])
    op.create_index("ix_faults_maintenance_record_id", "faults", ["maintenance_record_id"])
    op.create_index("ix_faults_created_by_id", "faults", ["created_by_id"])

    op.create_table(
        "repairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fault_id", sa.Integer(), nullable=False),
        sa.Column("repair_date", sa.Date(), nullable=False),
        sa.Column("meter_value", sa.Numeric(10, 1), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("technician", sa.String(120), nullable=True),
        sa.Column("workshop", sa.String(120), nullable=True),
        sa.Column("labor_hours", sa.Numeric(8, 1), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fault_id"], ["faults.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name="ck_repair_status",
        ),
        sa.CheckConstraint(
            "labor_hours IS NULL OR labor_hours >= 0",
            name="ck_repair_labor_hours_nonnegative",
        ),
        sa.CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="ck_repair_meter_nonnegative",
        ),
    )
    op.create_index("ix_repairs_id", "repairs", ["id"])
    op.create_index("ix_repairs_fault_id", "repairs", ["fault_id"])
    op.create_index("ix_repairs_created_by_id", "repairs", ["created_by_id"])

    op.create_table(
        "spare_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_number", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False, server_default="قطعة"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("part_number", name="uq_spare_part_number"),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_spare_part_active"),
    )
    op.create_index("ix_spare_parts_id", "spare_parts", ["id"])
    op.create_index("ix_spare_parts_part_number", "spare_parts", ["part_number"])

    op.create_table(
        "repair_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repair_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["repair_id"], ["repairs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("repair_id", "spare_part_id", name="uq_repair_spare_part"),
        sa.CheckConstraint("quantity > 0", name="ck_repair_part_quantity_positive"),
    )
    op.create_index("ix_repair_parts_id", "repair_parts", ["id"])
    op.create_index("ix_repair_parts_repair_id", "repair_parts", ["repair_id"])
    op.create_index("ix_repair_parts_spare_part_id", "repair_parts", ["spare_part_id"])


def downgrade() -> None:
    op.drop_table("repair_parts")
    op.drop_table("spare_parts")
    op.drop_table("repairs")
    op.drop_table("faults")
