"""Track the received request item behind each spare-part movement item."""

from alembic import op
import sqlalchemy as sa

revision = "9cff3cadf131"
down_revision = "merge_spare_parts_received_stage14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # This migration may be reached by tests/old databases that predate the
    # movement tables.  In that case there is nothing to alter; create_all()
    # already creates the current schema and stamps the migration head.
    if "spare_part_movement_items" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("spare_part_movement_items")}
    indexes = {index["name"] for index in inspector.get_indexes("spare_part_movement_items")}

    with op.batch_alter_table("spare_part_movement_items", schema=None) as batch_op:
        if "received_request_item_id" not in columns:
            batch_op.add_column(
                sa.Column("received_request_item_id", sa.Integer(), nullable=True)
            )
        batch_op.create_foreign_key(
            "fk_spare_part_movement_items_received_request_item_id",
            "spare_part_request_items",
            ["received_request_item_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    if "ix_spare_part_movement_items_received_request_item_id" not in indexes:
        op.create_index(
            "ix_spare_part_movement_items_received_request_item_id",
            "spare_part_movement_items",
            ["received_request_item_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "spare_part_movement_items" not in set(inspector.get_table_names()):
        return

    indexes = {index["name"] for index in inspector.get_indexes("spare_part_movement_items")}
    if "ix_spare_part_movement_items_received_request_item_id" in indexes:
        op.drop_index(
            "ix_spare_part_movement_items_received_request_item_id",
            table_name="spare_part_movement_items",
        )

    columns = {column["name"] for column in inspector.get_columns("spare_part_movement_items")}
    if "received_request_item_id" in columns:
        with op.batch_alter_table("spare_part_movement_items", schema=None) as batch_op:
            batch_op.drop_constraint(
                "fk_spare_part_movement_items_received_request_item_id",
                type_="foreignkey",
            )
            batch_op.drop_column("received_request_item_id")
