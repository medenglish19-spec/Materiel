"""Allow a spare part request item to carry a free-text name.

The item may now be named freely instead of being forced to reference the
spare parts register: ``spare_part_id`` becomes optional and ``part_name``
stores the name as typed. Existing rows keep their library link and get
``part_name`` back-filled from it, so nothing is lost.
"""

from alembic import op
import sqlalchemy as sa

revision = "spare_part_request_item_free_name"
down_revision = "add_received_date_spare_part_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("spare_part_request_items") as batch:
        batch.add_column(sa.Column("part_name", sa.String(length=200), nullable=True))
        batch.alter_column("spare_part_id", existing_type=sa.Integer(), nullable=True)

    # Existing rows keep pointing at the register; recover the name they used
    # to render through the relationship so the free-text column is never blank.
    op.execute(
        "UPDATE spare_part_request_items "
        "SET part_name = (SELECT name FROM spare_parts "
        "WHERE spare_parts.id = spare_part_request_items.spare_part_id) "
        "WHERE part_name IS NULL AND spare_part_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM spare_part_request_items "
        "WHERE spare_part_id IS NULL"
    )
    with op.batch_alter_table("spare_part_request_items") as batch:
        batch.drop_column("part_name")
        batch.alter_column("spare_part_id", existing_type=sa.Integer(), nullable=False)