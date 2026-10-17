"""Honour the SET NULL the schema already declares on orphaned spec definitions.

Every FK on this database carries an explicit ``on_delete``, and 27 of them say
``SET NULL``. ``equipment_model_spec_definitions.category_id`` is one of them:
the schema's answer to "the category was deleted" is "leave the definition, drop
the link". The 53 rows pointing at category 3 are exactly that situation that
SQLite never enforced, so the column still holds an id that no longer exists.

So this does what the constraint said it would do: clear the dangling id and
keep the row. What stays is the content those rows exist to hold -- their
``name``, ``code``, ``unit``, ``group_name`` -- and the
``equipment_model_spec_values`` rows hanging off them by
``spec_definition_id``. Deleting them instead would discard all of that, which
is why the earlier junction-table cleanup did not extend here: that table's FK
says CASCADE, so deleting the links *was* the declared behaviour, while this
one says SET NULL and deleting would contradict it.

The update is written as "rows that violate the foreign key" so it is a no-op on
a fresh database, and it only touches columns whose FK actually declares
``SET NULL`` -- read from the database, not assumed from the model. A column
that says CASCADE keeps its rows, because for those the declared answer is
deletion and stage13 is where that gets handled.
"""

from alembic import op
import sqlalchemy as sa

revision = "stage14_null_orphaned_spec_categories"
down_revision = "stage13_remove_orphaned_spec_links"
branch_labels = None
depends_on = None

TARGET_TABLE = "equipment_model_spec_definitions"
SET_NULL = "SET NULL"


def _set_null_columns(bind) -> list[tuple[str, str]]:
    """(column, parent table) for FKs on TARGET_TABLE declared SET NULL.

    Read from ``PRAGMA foreign_key_list`` rather than from the SQLAlchemy
    inspector, because the inspector reports ``options={}`` for tables it
    reflects in some cases -- verified on an in-memory table whose DDL plainly
    said ``ON DELETE SET NULL``. Trusting it there would make this migration a
    silent no-op, clearing nothing and recording itself as applied. The pragma
    reports the declared action in both cases.
    """
    pairs: list[tuple[str, str]] = []
    # A table-valued pragma accepts a parameter in modern SQLite, but not the
    # bound-parameter form every driver will send here, so the table name is
    # quoted as an identifier instead. It is a module constant, not user input.
    rows = bind.execute(
        sa.text(f"PRAGMA foreign_key_list('{TARGET_TABLE}')")
    ).fetchall()

    # PRAGMA foreign_key_list returns one row per column of a composite FK, and
    # repeats the parent for each: group by (id, seq) to keep composite keys whole.
    grouped: dict[tuple[int, int], dict] = {}
    for row in rows:
        mapping = dict(row._mapping)
        key = (mapping["id"], mapping["seq"])
        entry = grouped.setdefault(key, {
            "on_delete": (mapping["on_delete"] or "").upper(),
            "parent": mapping["table"],
            "columns": [],
        })
        entry["columns"].append(mapping["from"])

    for entry in grouped.values():
        if entry["on_delete"] != SET_NULL:
            continue
        if not entry["parent"] or len(entry["columns"]) != 1:
            # a composite or unnamed FK: not something to clear blindly
            continue
        pairs.append((entry["columns"][0], entry["parent"]))

    return pairs


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TARGET_TABLE not in set(inspector.get_table_names()):
        # a database that never had the table has nothing to repair
        return

    for column, parent in _set_null_columns(bind):
        if parent not in set(inspector.get_table_names()):
            continue

        # NOT EXISTS rather than NOT IN: a NULL id anywhere would make NOT IN
        # match nothing and quietly clear the whole column.
        bind.execute(
            sa.text(
                f"UPDATE {TARGET_TABLE} AS spec "
                f"SET {column} = NULL "
                f"WHERE {column} IS NOT NULL "
                f"AND NOT EXISTS ("
                f"  SELECT 1 FROM {parent} AS parent "
                f"  WHERE parent.id = spec.{column}"
                f")"
            )
        )


def downgrade() -> None:
    """The dangling ids are not restored, and cannot be.

    They named categories that no longer exist, so writing them back would
    recreate the violation this migration clears. If those categories are ever
    recreated, re-link the definitions deliberately -- which is a decision, not
    an undo. Nothing else about the rows changes: the names, codes, units and
    child values were never touched.
    """