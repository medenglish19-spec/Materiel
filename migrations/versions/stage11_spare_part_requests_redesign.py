"""Redesign spare-parts requests for the two-page workflow."""
from alembic import op
import sqlalchemy as sa

revision = "stage11_spare_part_requests_redesign"
down_revision = "stage10_spare_part_requests"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("spare_part_requests") as batch:
        batch.drop_constraint("ck_spare_part_request_source_type", type_="check")
        batch.drop_constraint("ck_spare_part_request_status", type_="check")
        batch.drop_constraint("ck_spare_part_request_priority", type_="check")
        batch.drop_constraint("ck_spare_part_request_source_match", type_="check")
        batch.add_column(sa.Column("fault_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_spare_part_request_fault", "faults", ["fault_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_spare_part_request_fault", ["fault_id"])
        batch.alter_column("request_number", existing_type=sa.String(length=50), type_=sa.String(length=80))
        batch.alter_column("status", existing_type=sa.String(length=30), type_=sa.String(length=20), server_default="pending")
        batch.create_check_constraint(
            "ck_spare_part_request_source_type",
            "source_type IN ('fault', 'repair')",
        )
        batch.create_check_constraint(
            "ck_spare_part_request_status",
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
        )
        batch.create_check_constraint(
            "ck_spare_part_request_source_match",
            "(source_type = 'fault' AND fault_id IS NOT NULL AND repair_id IS NULL) OR "
            "(source_type = 'repair' AND repair_id IS NOT NULL AND fault_id IS NULL)",
        )

    with op.batch_alter_table("spare_part_request_items") as batch:
        batch.drop_constraint("ck_spare_part_request_item_approved_nonnegative", type_="check")
        batch.drop_constraint("ck_spare_part_request_item_issued_nonnegative", type_="check")
        batch.drop_constraint("ck_spare_part_request_item_approved_lte_requested", type_="check")
        batch.drop_constraint("ck_spare_part_request_item_issued_lte_approved", type_="check")
        batch.add_column(sa.Column("received_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"))
        batch.add_column(sa.Column("recipient", sa.String(160), nullable=True))
        batch.add_column(sa.Column("supplier_institution", sa.String(200), nullable=True))
        batch.create_check_constraint(
            "ck_spare_part_request_item_received_nonnegative",
            "received_quantity >= 0",
        )
        batch.create_index("ix_spare_part_request_item_received", ["received_quantity"])


def downgrade():
    with op.batch_alter_table("spare_part_request_items") as batch:
        batch.drop_index("ix_spare_part_request_item_received")
        batch.drop_constraint("ck_spare_part_request_item_received_nonnegative", type_="check")
        batch.drop_column("supplier_institution")
        batch.drop_column("recipient")
        batch.drop_column("received_quantity")
        batch.create_check_constraint("ck_spare_part_request_item_issued_lte_approved", "issued_quantity <= approved_quantity")
        batch.create_check_constraint("ck_spare_part_request_item_approved_lte_requested", "approved_quantity <= requested_quantity")
        batch.create_check_constraint("ck_spare_part_request_item_issued_nonnegative", "issued_quantity >= 0")
        batch.create_check_constraint("ck_spare_part_request_item_approved_nonnegative", "approved_quantity >= 0")

    with op.batch_alter_table("spare_part_requests") as batch:
        batch.drop_constraint("ck_spare_part_request_source_match", type_="check")
        batch.drop_constraint("ck_spare_part_request_status", type_="check")
        batch.drop_constraint("ck_spare_part_request_source_type", type_="check")
        batch.drop_index("ix_spare_part_request_fault")
        batch.drop_constraint("fk_spare_part_request_fault", type_="foreignkey")
        batch.drop_column("fault_id")
        batch.alter_column("status", existing_type=sa.String(length=20), type_=sa.String(length=30))
        batch.alter_column("request_number", existing_type=sa.String(length=80), type_=sa.String(length=50))
        batch.create_check_constraint("ck_spare_part_request_priority", "priority IN ('normal', 'urgent')")
        batch.create_check_constraint("ck_spare_part_request_source_type", "source_type IN ('maintenance', 'repair', 'tire', 'battery')")
        batch.create_check_constraint("ck_spare_part_request_status", "status IN ('pending', 'approved', 'partially_fulfilled', 'fulfilled', 'rejected', 'cancelled')")
        batch.create_check_constraint(
            "ck_spare_part_request_source_match",
            "(source_type = 'maintenance' AND maintenance_record_id IS NOT NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'repair' AND maintenance_record_id IS NULL AND repair_id IS NOT NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'tire' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NOT NULL AND battery_id IS NULL) OR "
            "(source_type = 'battery' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NOT NULL)",
        )
