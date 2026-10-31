"""Route tire and battery intake through received request items.

Keep the old asset_receipts rows and foreign keys as historical audit data.
"""
from alembic import op
import sqlalchemy as sa


revision = "20261025_unify_asset_receiving"
down_revision = "20261024_fuel_model_consumption_rates"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    item_columns = {column["name"] for column in inspector.get_columns("spare_part_request_items")}
    item_checks = {check["name"] for check in inspector.get_check_constraints("spare_part_request_items")}
    if "asset_type" not in item_columns or "ck_spare_part_request_item_asset_type" not in item_checks:
        with op.batch_alter_table("spare_part_request_items") as batch:
            if "asset_type" not in item_columns:
                batch.add_column(sa.Column("asset_type", sa.String(20), nullable=False, server_default="part"))
            if "ck_spare_part_request_item_asset_type" not in item_checks:
                batch.create_check_constraint(
                    "ck_spare_part_request_item_asset_type",
                    "asset_type IN ('part', 'tire', 'battery')",
                )
    item_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("spare_part_request_items")}
    if "asset_type" in {column["name"] for column in sa.inspect(bind).get_columns("spare_part_request_items")} and "ix_spare_part_request_items_asset_type" not in item_indexes:
        op.create_index("ix_spare_part_request_items_asset_type", "spare_part_request_items", ["asset_type"])

    for table in ("tires", "batteries"):
        inspector = sa.inspect(bind)
        columns = {column["name"] for column in inspector.get_columns(table)}
        column_name = "acquisition_request_item_id"
        fk_name = f"fk_{table}_{column_name}_spare_part_request_items"
        foreign_keys = {foreign_key.get("name") for foreign_key in inspector.get_foreign_keys(table)}
        if column_name not in columns or fk_name not in foreign_keys:
            with op.batch_alter_table(table) as batch:
                if column_name not in columns:
                    batch.add_column(sa.Column(column_name, sa.Integer(), nullable=True))
                if fk_name not in foreign_keys:
                    batch.create_foreign_key(
                        fk_name,
                        "spare_part_request_items",
                        [column_name],
                        ["id"],
                        ondelete="RESTRICT",
                    )
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        if column_name in {column["name"] for column in sa.inspect(bind).get_columns(table)} and f"ix_{table}_{column_name}" not in indexes:
            op.create_index(f"ix_{table}_{column_name}", table, [column_name])


def downgrade():
    bind = op.get_bind()
    for table in ("batteries", "tires"):
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table)}
        if "acquisition_request_item_id" in columns:
            op.drop_index(f"ix_{table}_acquisition_request_item_id", table_name=table)
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(
                    f"fk_{table}_acquisition_request_item_id_spare_part_request_items",
                    type_="foreignkey",
                )
                batch.drop_column("acquisition_request_item_id")

    item_columns = {column["name"] for column in sa.inspect(bind).get_columns("spare_part_request_items")}
    if "asset_type" in item_columns:
        op.drop_index("ix_spare_part_request_items_asset_type", table_name="spare_part_request_items")
        with op.batch_alter_table("spare_part_request_items") as batch:
            batch.drop_constraint("ck_spare_part_request_item_asset_type", type_="check")
            batch.drop_column("asset_type")
