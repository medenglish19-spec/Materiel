"""Redesign spare-parts requests for the two-page workflow."""
from alembic import op
import sqlalchemy as sa

revision = "stage11_spare_part_requests_redesign"
down_revision = "stage10_spare_part_requests"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "spare_part_requests" in inspector.get_table_names():
        if bind.execute(sa.text("SELECT COUNT(*) FROM spare_part_requests")).scalar():
            raise RuntimeError("Cannot redesign spare_part_requests while it contains data.")
        op.drop_table("spare_part_request_items")
        op.drop_table("spare_part_requests")

    op.create_table(
        "spare_part_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_number", sa.String(80), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("fault_id", sa.Integer(), nullable=True),
        sa.Column("repair_id", sa.Integer(), nullable=True),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["fault_id"], ["faults.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["repair_id"], ["repairs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("request_number", name="uq_spare_part_request_number"),
        sa.CheckConstraint("source_type IN ('fault', 'repair')", name="ck_spare_part_request_source_type"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_spare_part_request_status"),
        sa.CheckConstraint(
            "(source_type = 'fault' AND fault_id IS NOT NULL AND repair_id IS NULL) OR "
            "(source_type = 'repair' AND repair_id IS NOT NULL AND fault_id IS NULL)",
            name="ck_spare_part_request_source_match",
        ),
    )
    for name, columns in [
        ("ix_spare_part_request_number", ["request_number"]),
        ("ix_spare_part_request_date", ["request_date"]),
        ("ix_spare_part_request_source_type", ["source_type"]),
        ("ix_spare_part_request_status", ["status"]),
        ("ix_spare_part_request_fault", ["fault_id"]),
        ("ix_spare_part_request_repair", ["repair_id"]),
        ("ix_spare_part_request_equipment", ["equipment_id"]),
    ]:
        op.create_index(name, "spare_part_requests", columns)

    op.create_table(
        "spare_part_request_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("received_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("recipient", sa.String(160), nullable=True),
        sa.Column("supplier_institution", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["spare_part_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("request_id", "spare_part_id", name="uq_spare_part_request_item_part"),
        sa.CheckConstraint("requested_quantity > 0", name="ck_spare_part_request_item_requested_positive"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_spare_part_request_item_received_nonnegative"),
    )
    op.create_index("ix_spare_part_request_item_request", "spare_part_request_items", ["request_id"])
    op.create_index("ix_spare_part_request_item_part", "spare_part_request_items", ["spare_part_id"])


def downgrade():
    op.drop_index("ix_spare_part_request_item_part", table_name="spare_part_request_items")
    op.drop_index("ix_spare_part_request_item_request", table_name="spare_part_request_items")
    op.drop_table("spare_part_request_items")
    for name in [
        "ix_spare_part_request_equipment", "ix_spare_part_request_repair",
        "ix_spare_part_request_fault", "ix_spare_part_request_status",
        "ix_spare_part_request_source_type", "ix_spare_part_request_date",
        "ix_spare_part_request_number",
    ]:
        op.drop_index(name, table_name="spare_part_requests")
    op.drop_table("spare_part_requests")
