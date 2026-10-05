"""stage13 removes dead spec links -- and only the dead ones.

The distinction the whole migration rests on: a junction row whose equipment type
was deleted carries no information of its own, while a spec definition row that
lost its category does. Deleting the first is housekeeping; deleting the second
destroys content. So the tests here check both halves -- the orphans go, and
everything a live row was carrying stays.

Running them against a database stamped at stage12 is also the proof: the orphans
are there before the migration and gone after it, on the same data.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MERGE = "merge_spare_parts_heads_0034_receipt"
STAGE12 = "stage12_spare_parts_complete"
STAGE13 = "stage13_remove_orphaned_spec_links"

# what the live database looks like: three surviving types, links to types 2..13
SURVIVING_TYPES = [39, 40, 41]
DEAD_TYPES = list(range(2, 14))


def _with_spec_tables(path: Path, live_types=None, dead_types=()) -> Path:
    """A database at stage12 with the two spec tables and some broken links."""
    live_types = SURVIVING_TYPES if live_types is None else live_types
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE equipment_types (id INTEGER PRIMARY KEY)")
        for type_id in live_types:
            con.execute("INSERT INTO equipment_types VALUES (?)", (type_id,))
        con.execute(
            "CREATE TABLE equipment_type_spec_definitions ("
            "equipment_type_id INTEGER NOT NULL REFERENCES equipment_types (id),"
            "spec_definition_id INTEGER NOT NULL)"
        )
        for offset, type_id in enumerate(dead_types):
            con.execute(
                "INSERT INTO equipment_type_spec_definitions VALUES (?, ?)",
                (type_id, 100 + offset),
            )
        con.execute(
            "INSERT INTO equipment_type_spec_definitions VALUES (?, ?)",
            (live_types[0], 900),
        )
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (STAGE12,))
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


def _links(path: Path) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return sorted(con.execute(
            "SELECT equipment_type_id, spec_definition_id "
            "FROM equipment_type_spec_definitions").fetchall())
    finally:
        con.close()


def _stamp(path: Path) -> str:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()


def test_the_orphans_are_gone_after_upgrading(tmp_path):
    db = _with_spec_tables(tmp_path / "orphans.db", dead_types=DEAD_TYPES)
    assert len(_links(db)) == len(DEAD_TYPES) + 1, "the fixture is not broken"

    _migrate(db)

    remaining = _links(db)
    assert all(type_id in SURVIVING_TYPES for type_id, _ in remaining), remaining
    assert len(remaining) == 1, f"a live link was removed as well: {remaining}"


def test_a_link_to_a_real_type_survives(tmp_path):
    db = _with_spec_tables(tmp_path / "live.db", dead_types=[2, 3])

    _migrate(db)

    assert _links(db) == [(SURVIVING_TYPES[0], 900)]


def test_a_live_link_is_not_touched_when_there_are_no_orphans(tmp_path):
    db = _with_spec_tables(tmp_path / "clean.db")

    _migrate(db)

    assert _links(db) == [(SURVIVING_TYPES[0], 900)]


def test_nothing_is_deleted_when_the_table_is_empty(tmp_path):
    db = _with_spec_tables(tmp_path / "empty.db")
    con = sqlite3.connect(db)
    try:
        con.execute("DELETE FROM equipment_type_spec_definitions")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    assert _links(db) == []


def test_a_database_without_the_spec_tables_is_left_alone(tmp_path):
    """Older shapes must not crash the migration on the way past."""
    db = tmp_path / "bare.db"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (STAGE12,))
        con.commit()
    finally:
        con.close()

    _migrate(db)

    assert _stamp(db) == STAGE13
    tables = sqlite3.connect(db).execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert [t[0] for t in tables if t[0].startswith("equipment")] == []


def test_null_links_are_not_deleted(tmp_path):
    """NOT IN would wipe these; NOT EXISTS must not."""
    db = _with_spec_tables(tmp_path / "nulls.db")
    con = sqlite3.connect(db)
    try:
        con.execute("DROP TABLE equipment_type_spec_definitions")
        con.execute(
            "CREATE TABLE equipment_type_spec_definitions ("
            "equipment_type_id INTEGER REFERENCES equipment_types (id),"
            "spec_definition_id INTEGER)"
        )
        con.execute(
            "INSERT INTO equipment_type_spec_definitions VALUES (NULL, 1)")
        con.execute(
            "INSERT INTO equipment_type_spec_definitions VALUES (999, 2)")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    assert _links(db) == [(None, 1)], "a NULL link is not a violation"


def test_the_migration_records_itself(tmp_path):
    db = _with_spec_tables(tmp_path / "stamp.db", dead_types=[2, 3])

    _migrate(db)

    assert _stamp(db) == STAGE13
    assert STAGE12 in (ROOT / "migrations" / "versions" /
                       "stage13_remove_orphaned_spec_links.py").read_text(
                           encoding="utf-8")


def test_the_real_spec_definitions_are_left_for_their_owner(tmp_path):
    """The 53 content-bearing rows are a decision, not a cleanup.

    This one is behavioural rather than a check on the migration's text: rows
    that violate a foreign key but carry real content must survive, because
    whether to restore the categories or null the column is not this
    migration's call to make.
    """
    db = _with_spec_tables(tmp_path / "content.db", dead_types=[2, 3])
    con = sqlite3.connect(db)
    try:
        con.execute(
            "CREATE TABLE equipment_categories (id INTEGER PRIMARY KEY)")
        con.execute("INSERT INTO equipment_categories VALUES (9)")
        con.execute(
            "CREATE TABLE equipment_model_spec_definitions ("
            "id INTEGER PRIMARY KEY, name TEXT, category_id INTEGER "
            "REFERENCES equipment_categories (id))"
        )
        # category 3 does not exist, so this row is orphaned -- and it is real
        con.execute(
            "INSERT INTO equipment_model_spec_definitions VALUES (1, 'الصانع', 3)")
        con.commit()
    finally:
        con.close()

    _migrate(db)

    con = sqlite3.connect(db)
    try:
        survivors = con.execute(
            "SELECT id, name, category_id FROM equipment_model_spec_definitions"
        ).fetchall()
    finally:
        con.close()

    assert survivors == [(1, "الصانع", 3)], (
        f"the migration deleted content-bearing rows it was told to leave alone: "
        f"{survivors}"
    )