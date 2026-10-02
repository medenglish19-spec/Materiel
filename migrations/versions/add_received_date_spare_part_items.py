"""Add received date to spare part request items."""

from alembic import op

revision = "add_received_date_spare_part_items"
down_revision = "merge_stage11_c3a9e7f21d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE spare_part_request_items ADD COLUMN received_date DATE")
    op.create_index("ix_spare_part_request_items_received_date", "spare_part_request_items", ["received_date"])


def downgrade() -> None:
    op.drop_index("ix_spare_part_request_items_received_date", table_name="spare_part_request_items")
    op.drop_column("spare_part_request_items", "received_date")
