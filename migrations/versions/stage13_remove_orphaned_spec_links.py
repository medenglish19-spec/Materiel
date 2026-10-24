"""Delete spec links whose equipment type no longer exists.

``equipment_type_spec_definitions`` is a pure junction table: it carries no data
of its own, only ``(equipment_type_id, spec_definition_id)`` pairs. Every row in
this database pointed at an ``equipment_types`` row that has since been deleted
-- the surviving types are 39, 40 and 41 while the links reference 2 through 13
-- so all 651 rows were dead. Every ``spec_definition_id`` they reference still
exists in ``equipment_model_spec_definitions``, which is what makes removing them
lossless rather than merely tidy.

The delete is written as "rows that violate the foreign key" instead of "all
rows" so it is a no-op on a fresh database, and removes only a given install's
own dead links wherever they are found. SQLite does not enforce foreign keys,
which is how a link outlives the type it named.

``equipment_model_spec_definitions`` has orphaned rows too, but they carry real
content (spec names in Arabic) and only 53 of its 86 rows are affected, so they
are deliberately left alone: whether to bring the categories back or null the
column is a decision for whoever owns that feature, not something to decide by
deleting their data.
"""

from alembic import op
import sqlalchemy as sa

revision = "stage13_remove_orphaned_spec_links"
down_revision = "stage12_spare_parts_complete"
branch_labels = None
depends_on = None

LINK_TABLE = "equipment_type_spec_definitions"
TYPE_TABLE = "equipment_types"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    # a database that never had these tables has nothing to repair
    if LINK_TABLE not in existing or TYPE_TABLE not in existing:
        return

    columns = {c["name"] for c in inspector.get_columns(LINK_TABLE)}
    if "equipment_type_id" not in columns:
        return

    # NOT EXISTS rather than NOT IN: a NULL id on either side would make NOT IN
    # match nothing and quietly delete the whole table's contents.
    bind.execute(
        sa.text(
            f"DELETE FROM {LINK_TABLE} AS link "
            f"WHERE link.equipment_type_id IS NOT NULL "
            f"AND NOT EXISTS ("
            f"  SELECT 1 FROM {TYPE_TABLE} AS parent "
            f"  WHERE parent.id = link.equipment_type_id"
            f")"
        )
    )


def downgrade() -> None:
    """The rows are not restored, and that is the point.

    They named equipment types that no longer exist, so putting them back would
    recreate exactly the corruption this migration removes. If those types are
    ever needed again, recreate the types and re-link the specs deliberately --
    which is a decision, not an undo.
    """