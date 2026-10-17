"""Allow a spare part request item to carry a free-text name.

The item may now be named freely instead of being forced to reference the
spare parts register: ``spare_part_id`` becomes optional and ``part_name``
stores the name as typed. Existing rows keep their library link and get
``part_name`` back-filled from it, so nothing is lost.
"""

from alembic import op
import sqlalchemy as sa

revision = "spare_part_request_item_free_name"
down_revision = "free_text_spare_part_names"
branch_labels = None
depends_on = None

TABLE = "spare_part_request_items"


def _columns():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if "spare_part_name" in _columns() and "part_name" not in _columns():
        # Databases stamped with the deleted revision carry the earlier
        # spelling. Reuse it instead of dropping the stored names.
        op.execute(f"ALTER TABLE {TABLE} RENAME COLUMN spare_part_name TO part_name")
    with op.batch_alter_table(TABLE) as batch:
        if "part_name" not in _columns():
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
    columns = _columns()
    if "part_name" in columns and "spare_part_name" not in columns:
        op.execute(f"ALTER TABLE {TABLE} RENAME COLUMN part_name TO spare_part_name")
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("spare_part_id", existing_type=sa.Integer(), nullable=False)
