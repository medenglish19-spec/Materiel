"""Track the received request item behind each spare-part movement item."""

from alembic import op
import sqlalchemy as sa

revision = "9cff3cadf131"
down_revision = "add_received_date_spare_part_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "spare_part_movement_items",
        sa.Column("received_request_item_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_spare_part_movement_items_received_request_item_id",
        "spare_part_movement_items",
        ["received_request_item_id"],
    )
    op.create_foreign_key(
        "fk_spare_part_movement_items_received_request_item_id",
        "spare_part_movement_items",
        "spare_part_request_items",
        ["received_request_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_spare_part_movement_items_received_request_item_id",
        "spare_part_movement_items",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_spare_part_movement_items_received_request_item_id",
        table_name="spare_part_movement_items",
    )
    op.drop_column("spare_part_movement_items", "received_request_item_id")
