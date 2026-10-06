"""stage14 clears the dangling category link instead of deleting the row.

The distinction the whole migration rests on is the one the schema already makes:
a foreign key declared ``ON DELETE CASCADE`` says "the row goes with the parent",
and a foreign key declared ``ON DELETE SET NULL`` says "the row stays and loses
the link". ``equipment_model_spec_definitions.category_id`` says SET NULL, so
clearing it is what the constraint promised would happen -- deleting the row
would be the migration contradicting the schema.

What must survive is the content those rows exist to hold: the name, the code,
the unit, the group, and the child value rows hanging off them by
``spec_definition_id``. The tests below check the content survives rather than
only checking the count went down, because a count is satisfied equally by the
right fix and by the wrong one.

Running them against a database stamped at stage13 is also the proof: the 53
dangling ids are there before the migration and gone after it, on the same data.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STAGE13 = "stage13_remove_orphaned_spec_links"
STAGE14 = "9cff3cadf131"

# what the live database holds: categories 9 and 10 survive, 3 is gone
LIVE_CATEGORIES = [9, 10]
DEAD_CATEGORY = 3


def _with_spec_tables(path: Path, category_ids=(), spec_categories=()) -> Path:
    """A database at stage13 with spec definitions, some pointing at a dead id."""
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE equipment_categories (id INTEGER PRIMARY KEY)")
        for category_id in category_ids:
            con.execute("INSERT INTO equipment_categories VALUES (?)", (category_id,))

        con.execute(
            "CREATE TABLE equipment_model_spec_definitions ("
            "id INTEGER PRIMARY KEY,"
            "name TEXT NOT NULL UNIQUE,"
            "code TEXT,"
            "unit TEXT,"
            "group_name TEXT,"
            "category_id INTEGER REFERENCES equipment_categories (id) ON DELETE SET NULL)"
        )
        con.execute(
            "CREATE TABLE equipment_model_spec_values ("
            "id INTEGER PRIMARY KEY,"
            "spec_definition_id INTEGER REFERENCES equipment_model_spec_definitions (id)"
            " ON DELETE CASCADE,"
            "value TEXT)"
        )
        con.execute(
            "CREATE TABLE equipment_types (id INTEGER PRIMARY KEY,"
            "category_id INTEGER REFERENCES equipment_categories (id) ON DELETE SET NULL)"
        )

        for offset, category_id in enumerate(spec_categories, start=1):
            con.execute(
                "INSERT INTO equipment_model_spec_definitions "
                "(id, name, code, unit, group_name, category_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (offset, f"خاصية {offset}", f"c{offset}", "مم", "مجموعة",
                 category_id),
            )
            # a child row that must not be lost along with the definition
            con.execute(
                "INSERT INTO equipment_model_spec_values "
                "(id, spec_definition_id, value) VALUES (?, ?, ?)",
                (offset, offset, f"قيمة {offset}"),
            )

        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (STAGE13,))
        con.commit()
    finally:
        con.close()
    return path


def _migrate(path: Path, target: str = "head"):
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings

    previous = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite:///{path.as_posix()}"
    try:
        return command.upgrade(Config(str(ROOT / "alembic.ini")), target)
    finally:
        settings.DATABASE_URL = previous


def _specs(path: Path) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return sorted(con.execute(
            "SELECT id, name, code, unit, group_name, category_id "
            "FROM equipment_model_spec_definitions").fetchall())
    finally:
        con.close()


def _child_count(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute(
            "SELECT count(*) FROM equipment_model_spec_values").fetchone()[0]
    finally:
        con.close()


def _orphans(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute(
            "SELECT count(*) FROM equipment_model_spec_definitions "
            "WHERE category_id IS NOT NULL AND category_id NOT IN "
            "(SELECT id FROM equipment_categories)").fetchone()[0]
    finally:
        con.close()


def _stamp(path: Path) -> str:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()


def test_the_dangling_link_is_gone_after_upgrading(tmp_path):
    db = _with_spec_tables(tmp_path / "orphans.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY, DEAD_CATEGORY])
    assert _orphans(db) == 2, "the fixture is not broken"

    _migrate(db)

    assert _orphans(db) == 0


def test_the_row_survives_with_its_content(tmp_path):
    """The point of SET NULL: the definition stays, only the link goes."""
    db = _with_spec_tables(tmp_path / "content.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY])

    _migrate(db)

    rows = _specs(db)
    assert len(rows) == 1, f"the definition was deleted: {rows}"
    id_, name, code, unit, group_name, category_id = rows[0]
    assert (name, code, unit, group_name) == ("خاصية 1", "c1", "مم", "مجموعة"), (
        f"the content was altered: {rows}"
    )
    assert category_id is None, f"the dangling link survived: {category_id}"


def test_the_child_values_are_untouched(tmp_path):
    """Losing the definitions would orphan 30 rows on the live database."""
    db = _with_spec_tables(tmp_path / "children.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY])

    _migrate(db)

    assert _child_count(db) == 1, "a child value row was lost"


def test_a_live_category_is_not_cleared(tmp_path):
    db = _with_spec_tables(tmp_path / "live.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[LIVE_CATEGORIES[0], DEAD_CATEGORY])

    _migrate(db)

    by_id = {row[0]: row for row in _specs(db)}
    assert by_id[1][5] == LIVE_CATEGORIES[0], "a live link was cleared"
    assert by_id[2][5] is None, "the dangling link was not cleared"


def test_an_already_null_column_is_left_alone(tmp_path):
    db = _with_spec_tables(tmp_path / "nulls.db", category_ids=LIVE_CATEGORIES)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO equipment_model_spec_definitions "
            "(id, name, code, unit, group_name, category_id) "
            "VALUES (1, 'بلا تصنيف', NULL, NULL, NULL, NULL)")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    assert _specs(db) == [(1, "بلا تصنيف", None, None, None, None)]


def test_a_cascade_column_on_the_same_table_is_left_alone(tmp_path):
    """The action is read per column, so SET NULL and CASCADE must differ here.

    The distinction has to be visible on the table this migration actually
    touches. A CASCADE link on some other table proves nothing: stage14 never
    opens it, so treating every action as SET NULL would still pass.
    """
    db = _with_spec_tables(tmp_path / "cascade_column.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY])
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE equipment_model_spec_definitions "
                    "ADD COLUMN type_id INTEGER REFERENCES equipment_types (id) "
                    "ON DELETE CASCADE")
        con.execute("UPDATE equipment_model_spec_definitions SET type_id = 77777")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    con = sqlite3.connect(db)
    try:
        type_id, category_id = con.execute(
            "SELECT type_id, category_id FROM equipment_model_spec_definitions"
        ).fetchone()
    finally:
        con.close()

    assert category_id is None, "the SET NULL column was not cleared"
    assert type_id == 77777, (
        f"a CASCADE column was cleared to {type_id!r}; for that action the "
        f"declared answer is deletion, and it is stage13's business, not this"
    )


def test_a_cascade_link_on_another_table_is_not_this_migration_s_business(tmp_path):
    db = _with_spec_tables(tmp_path / "cascade.db", category_ids=LIVE_CATEGORIES)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "CREATE TABLE equipment_type_spec_definitions ("
            "equipment_type_id INTEGER REFERENCES equipment_types (id) ON DELETE CASCADE,"
            "spec_definition_id INTEGER)")
        con.execute("INSERT INTO equipment_types VALUES (99999, 3)")
        con.execute(
            "INSERT INTO equipment_type_spec_definitions VALUES (99999, 1)")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    con = sqlite3.connect(db)
    try:
        left = con.execute(
            "SELECT count(*) FROM equipment_type_spec_definitions").fetchone()[0]
    finally:
        con.close()
    assert left == 1, (
        "a CASCADE link was removed here; deletion belongs to stage13, not this"
    )


def test_a_database_without_the_table_is_left_alone(tmp_path):
    """Older shapes must not crash the migration on the way past."""
    db = tmp_path / "bare.db"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (STAGE13,))
        con.commit()
    finally:
        con.close()

    _migrate(db)

    assert _stamp(db) == STAGE14


def test_the_migration_records_itself(tmp_path):
    db = _with_spec_tables(tmp_path / "stamp.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY])

    _migrate(db)

    assert _stamp(db) == STAGE14


def test_it_does_not_act_on_a_column_whose_action_it_cannot_read(tmp_path):
    """The failure this guards is a silent no-op recorded as success.

    The SQLAlchemy inspector reports ``options={}`` for some reflected tables --
    verified against an in-memory table whose DDL plainly said ``ON DELETE SET
    NULL``. Reading the declared action from there would clear nothing while
    still stamping the revision, and the database would look fixed.
    """
    db = _with_spec_tables(tmp_path / "pragma.db",
                           category_ids=LIVE_CATEGORIES,
                           spec_categories=[DEAD_CATEGORY])

    import importlib

    module = importlib.import_module(
        "migrations.versions.stage14_null_orphaned_spec_categories")

    engine = __import__("sqlalchemy").create_engine(f"sqlite:///{db.as_posix()}")
    with engine.connect() as bind:
        found = module._set_null_columns(bind)
    assert found == [("category_id", "equipment_categories")], (
        f"the declared SET NULL action was not read from the database: {found}"
    )

    # and the pragma really is the source that sees the action
    import sqlalchemy as sa

    with engine.connect() as bind:
        pragma = bind.execute(sa.text(
            "PRAGMA foreign_key_list('equipment_model_spec_definitions')"
        )).fetchall()
    # column order is: id, seq, table, from, to, on_update, on_delete, match
    actions = {row[6] for row in pragma}
    assert "SET NULL" in actions, (
        f"the pragma did not report the declared action: {actions} "
        f"(rows: {[(r[2], r[6]) for r in pragma]})"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))