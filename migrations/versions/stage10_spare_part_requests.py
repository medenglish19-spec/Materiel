"""Create the independent spare-parts request workflow.

Requests reuse the existing spare_parts master and can originate from
maintenance execution, repairs, tires, or batteries.
"""
from alembic import op
import sqlalchemy as sa

revision = "stage10_spare_part_requests"
down_revision = "stage9_seed_maintenance_operation_library"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "spare_part_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_number", sa.String(50), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("needed_by_date", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("maintenance_record_id", sa.Integer(), nullable=True),
        sa.Column("repair_id", sa.Integer(), nullable=True),
        sa.Column("tire_id", sa.Integer(), nullable=True),
        sa.Column("battery_id", sa.Integer(), nullable=True),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["maintenance_record_id"], ["maintenance_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["repair_id"], ["repairs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tire_id"], ["tires.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["battery_id"], ["batteries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("request_number", name="uq_spare_part_request_number"),
        sa.CheckConstraint(
            "source_type IN ('maintenance', 'repair', 'tire', 'battery')",
            name="ck_spare_part_request_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'partially_fulfilled', 'fulfilled', 'rejected', 'cancelled')",
            name="ck_spare_part_request_status",
        ),
        sa.CheckConstraint(
            "priority IN ('normal', 'urgent')",
            name="ck_spare_part_request_priority",
        ),
        sa.CheckConstraint(
            "(source_type = 'maintenance' AND maintenance_record_id IS NOT NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'repair' AND maintenance_record_id IS NULL AND repair_id IS NOT NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'tire' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NOT NULL AND battery_id IS NULL) OR "
            "(source_type = 'battery' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NOT NULL)",
            name="ck_spare_part_request_source_match",
        ),
    )
    for name, table, columns in [
        ("ix_spare_part_request_number", "spare_part_requests", ["request_number"]),
        ("ix_spare_part_request_date", "spare_part_requests", ["request_date"]),
        ("ix_spare_part_request_source_type", "spare_part_requests", ["source_type"]),
        ("ix_spare_part_request_status", "spare_part_requests", ["status"]),
        ("ix_spare_part_request_maintenance", "spare_part_requests", ["maintenance_record_id"]),
        ("ix_spare_part_request_repair", "spare_part_requests", ["repair_id"]),
        ("ix_spare_part_request_tire", "spare_part_requests", ["tire_id"]),
        ("ix_spare_part_request_battery", "spare_part_requests", ["battery_id"]),
        ("ix_spare_part_request_equipment", "spare_part_requests", ["equipment_id"]),
    ]:
        op.create_index(name, table, columns)

    op.create_table(
        "spare_part_request_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("issued_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["spare_part_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_id", "spare_part_id", name="uq_spare_part_request_item_part"),
        sa.CheckConstraint("requested_quantity > 0", name="ck_spare_part_request_item_requested_positive"),
        sa.CheckConstraint("approved_quantity >= 0", name="ck_spare_part_request_item_approved_nonnegative"),
        sa.CheckConstraint("issued_quantity >= 0", name="ck_spare_part_request_item_issued_nonnegative"),
        sa.CheckConstraint("approved_quantity <= requested_quantity", name="ck_spare_part_request_item_approved_lte_requested"),
        sa.CheckConstraint("issued_quantity <= approved_quantity", name="ck_spare_part_request_item_issued_lte_approved"),
    )
    op.create_index("ix_spare_part_request_item_request", "spare_part_request_items", ["request_id"])
    op.create_index("ix_spare_part_request_item_part", "spare_part_request_items", ["spare_part_id"])


def downgrade():
    op.drop_index("ix_spare_part_request_item_part", table_name="spare_part_request_items")
    op.drop_index("ix_spare_part_request_item_request", table_name="spare_part_request_items")
    op.drop_table("spare_part_request_items")
    for name in [
        "ix_spare_part_request_equipment", "ix_spare_part_request_battery",
        "ix_spare_part_request_tire", "ix_spare_part_request_repair",
        "ix_spare_part_request_maintenance", "ix_spare_part_request_status",
        "ix_spare_part_request_source_type", "ix_spare_part_request_date",
        "ix_spare_part_request_number",
    ]:
        op.drop_index(name, table_name="spare_part_requests")
    op.drop_table("spare_part_requests")
