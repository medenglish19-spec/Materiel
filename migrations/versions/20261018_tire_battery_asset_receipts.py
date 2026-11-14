"""Track tire/battery procurement and model batteries by type."""
from alembic import op
import sqlalchemy as sa


revision = "20261018_tire_battery_asset_receipts"
down_revision = "20261017_remove_repair_cancellation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("asset_receipts"):
        op.create_table(
            "asset_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("asset_type", sa.String(20), nullable=False),
            sa.Column("document_number", sa.String(100), nullable=False),
            sa.Column("description", sa.String(200), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("received_date", sa.Date(), nullable=False),
            sa.Column("supplier", sa.String(200), nullable=True),
            sa.Column("recipient", sa.String(160), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("asset_type IN ('tire', 'battery')", name="ck_asset_receipt_type"),
            sa.CheckConstraint("quantity > 0", name="ck_asset_receipt_quantity_positive"),
            sa.UniqueConstraint("document_number", name="uq_asset_receipt_document_number"),
        )
    for index_name, column in (
        ("ix_asset_receipts_asset_type", "asset_type"),
        ("ix_asset_receipts_document_number", "document_number"),
        ("ix_asset_receipts_received_date", "received_date"),
        ("ix_asset_receipts_id", "id"),
    ):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("asset_receipts")}
        if index_name not in indexes:
            op.create_index(index_name, "asset_receipts", [column])

    for table in ("tires", "batteries"):
        inspector = sa.inspect(bind)
        columns = {item["name"]: item for item in inspector.get_columns(table)}
        foreign_keys = {item.get("name") for item in inspector.get_foreign_keys(table)}
        add_receipt_column = "acquisition_receipt_id" not in columns
        add_type_column = table == "batteries" and "battery_type" not in columns
        allow_null_serial = table == "batteries" and not columns["serial_number"]["nullable"]
        fk_name = f"fk_{table}_acquisition_receipt_id_asset_receipts"
        if add_receipt_column or add_type_column or allow_null_serial or fk_name not in foreign_keys:
            with op.batch_alter_table(table) as batch:
                if allow_null_serial:
                    batch.alter_column("serial_number", existing_type=sa.String(80), nullable=True)
                if add_type_column:
                    batch.add_column(sa.Column("battery_type", sa.String(100), nullable=True))
                if add_receipt_column:
                    batch.add_column(sa.Column("acquisition_receipt_id", sa.Integer(), nullable=True))
                if fk_name not in foreign_keys:
                    batch.create_foreign_key(
                        fk_name, "asset_receipts", ["acquisition_receipt_id"], ["id"], ondelete="RESTRICT"
                    )
        index_name = f"ix_{table}_acquisition_receipt_id"
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
        if index_name not in indexes:
            op.create_index(index_name, table, ["acquisition_receipt_id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM batteries WHERE serial_number IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot restore required battery serial numbers after recording type-based batteries.")
    op.drop_index("ix_batteries_acquisition_receipt_id", table_name="batteries")
    with op.batch_alter_table("batteries") as batch:
        batch.drop_constraint("fk_batteries_acquisition_receipt_id_asset_receipts", type_="foreignkey")
        batch.drop_column("acquisition_receipt_id")
        batch.drop_column("battery_type")
        batch.alter_column("serial_number", existing_type=sa.String(80), nullable=False)
    op.drop_index("ix_tires_acquisition_receipt_id", table_name="tires")
    with op.batch_alter_table("tires") as batch:
        batch.drop_constraint("fk_tires_acquisition_receipt_id_asset_receipts", type_="foreignkey")
        batch.drop_column("acquisition_receipt_id")
    op.drop_index("ix_asset_receipts_id", table_name="asset_receipts")
    op.drop_index("ix_asset_receipts_received_date", table_name="asset_receipts")
    op.drop_index("ix_asset_receipts_document_number", table_name="asset_receipts")
    op.drop_index("ix_asset_receipts_asset_type", table_name="asset_receipts")
    op.drop_table("asset_receipts")
