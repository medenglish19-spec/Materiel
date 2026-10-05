"""The health check has to actually notice things.

A checker that reports "no problems" because it never asked the question is
worse than no checker: it gets trusted. So every rule below is proven against a
database seeded with that exact fault -- orphaned rows, a half-applied
batch_alter_table, a database behind head -- and against the read-only
guarantee, which is the property that makes it safe to point at the live file.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_db_health import check, main  # noqa: E402

HEAD = "stage12_spare_parts_complete"


def _fresh(path: Path, stamp: str = HEAD) -> Path:
    """A healthy database: one table, no rows, at head."""
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE equipment_types (id INTEGER PRIMARY KEY)")
        con.execute(
            "CREATE TABLE equipment_type_spec_definitions ("
            "id INTEGER PRIMARY KEY, equipment_type_id INTEGER NOT NULL "
            "REFERENCES equipment_types (id))"
        )
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (stamp,))
        con.commit()
    finally:
        con.close()
    return path


def _orphan_a_row(path: Path) -> None:
    """The fault this project actually has: a child row whose parent is gone.

    Inserted with foreign keys off, which is how they get there in practice --
    SQLite does not enforce them by default, so a row can outlive the parent it
    pointed at. foreign_key_check finds them regardless.
    """
    con = sqlite3.connect(path)
    try:
        con.execute(
            "INSERT INTO equipment_type_spec_definitions (id, equipment_type_id) "
            "VALUES (7, 404)"
        )
        con.commit()
    finally:
        con.close()


def test_a_healthy_database_reports_nothing(tmp_path):
    problems, warnings = check(_fresh(tmp_path / "ok.db"))

    assert problems == [], problems
    assert warnings == [], warnings


def test_an_orphaned_row_is_reported_with_where_to_look(tmp_path):
    db = _fresh(tmp_path / "orphan.db")
    _orphan_a_row(db)

    problems, _ = check(db)

    assert len(problems) == 1, problems
    assert "equipment_type_spec_definitions -> equipment_types" in problems[0]
    assert "rowid 7" in problems[0], problems[0]


def test_several_orphans_are_counted_not_just_found(tmp_path):
    db = _fresh(tmp_path / "many.db")
    _orphan_a_row(db)
    con = sqlite3.connect(db)
    try:
        con.executemany(
            "INSERT INTO equipment_type_spec_definitions (id, equipment_type_id) "
            "VALUES (?, 404)",
            [(8,), (9,)],
        )
        con.commit()
    finally:
        con.close()

    problems, _ = check(db)

    assert len(problems) == 1
    assert problems[0].startswith("3 orphaned row(s)"), problems[0]


def test_a_stray_temp_table_is_a_warning_not_a_silent_pass(tmp_path):
    """These are what break the retry after a migration aborts partway."""
    db = _fresh(tmp_path / "stray.db")
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE _alembic_tmp_spare_part_movement_documents (id INTEGER)")
        con.commit()
    finally:
        con.close()

    problems, warnings = check(db)

    assert not [p for p in problems if "stray" in p], "it should warn, not fail"
    assert any("_alembic_tmp_" in w for w in warnings), warnings


def test_a_database_behind_head_is_reported(tmp_path):
    db = _fresh(tmp_path / "behind.db", stamp="merge_spare_parts_heads_0034_receipt")

    problems, _ = check(db)

    assert any("alembic upgrade head" in p for p in problems), problems


def test_an_unmigrated_database_says_so(tmp_path):
    db = tmp_path / "blank.db"
    sqlite3.connect(db).close()

    problems, warnings = check(db)

    assert any("never migrated" in w for w in warnings), warnings
    assert problems == [], problems


def test_it_never_writes_to_the_database(tmp_path):
    """The whole reason it is safe to point at the live file."""
    db = _fresh(tmp_path / "ro.db")
    _orphan_a_row(db)
    before = db.read_bytes()

    check(db)
    main([str(db)])

    assert db.read_bytes() == before, "the health check modified the database"


def test_a_missing_file_fails_instead_of_creating_one(tmp_path):
    target = tmp_path / "not-there.db"

    with pytest.raises(SystemExit):
        check(target)

    assert not target.exists(), "it created the file it was asked to inspect"


def test_the_exit_code_is_non_zero_only_on_a_real_problem(tmp_path):
    healthy, _ = _fresh(tmp_path / "healthy.db"), None
    broken = _fresh(tmp_path / "broken.db")
    _orphan_a_row(broken)

    assert main([str(healthy)]) == 0
    assert main([str(broken)]) == 1
    assert main([str(broken), "--at-head-only"]) == 0


def test_the_check_agrees_with_the_live_database(tmp_path):
    """The real file must parse and answer, not just the fixtures."""
    live = ROOT / "fleet_assets.db"
    if not live.is_file():
        pytest.skip("no live database in this checkout")

    problems, warnings = check(live)

    assert all(isinstance(p, str) and p for p in problems)
    assert all(isinstance(w, str) and w for w in warnings)