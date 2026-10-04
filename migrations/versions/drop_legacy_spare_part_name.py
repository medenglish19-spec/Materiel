"""Drop the superseded `spare_part_name` column.

Databases that were stamped with the deleted revision ended up carrying both
spellings: `part_name` from the current revision and the earlier
`spare_part_name` beside it. Any name stored only in the older column is
copied across first, so dropping it destroys nothing.
"""

from alembic import op
import sqlalchemy as sa

revision = "drop_legacy_spare_part_name"
down_revision = "spare_part_request_item_free_name"
branch_labels = None
depends_on = None

TABLE = "spare_part_request_items"
LEGACY = "spare_part_name"
CURRENT = "part_name"


def _columns():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    columns = _columns()
    if LEGACY not in columns:
        return
    if CURRENT in columns:
        op.execute(
            f"UPDATE {TABLE} SET {CURRENT} = {LEGACY} "
            f"WHERE {CURRENT} IS NULL AND {LEGACY} IS NOT NULL"
        )
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column(LEGACY)
        return
    op.execute(f"ALTER TABLE {TABLE} RENAME COLUMN {LEGACY} TO {CURRENT}")


def downgrade() -> None:
    columns = _columns()
    if CURRENT not in columns or LEGACY in columns:
        return
    op.execute(f"ALTER TABLE {TABLE} RENAME COLUMN {CURRENT} TO {LEGACY}")
