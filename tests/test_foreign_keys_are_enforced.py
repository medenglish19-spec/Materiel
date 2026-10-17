"""SQLite must enforce the foreign keys the schema declares.

SQLite ships with foreign key enforcement off. Every ``ON DELETE`` in this
schema -- the 24 CASCADEs, the 27 SET NULLs -- was therefore decorative: nothing
enforced it, so a row could name a parent that had been deleted and SQLite would
accept it without complaint. That is how 704 orphaned rows accumulated, and why
the health check was the only thing that could see them.

Turning enforcement on is the step that stops it recurring. Two things have to
hold for it to be safe, and both are checked here: the database must have no
violations left to trip over at startup, and a new violation must actually be
refused rather than quietly stored.

The pragma is per connection, not per database, so the interesting case is the
*second* connection -- setting it once when the Engine is built would look
correct in a single-connection test and do nothing in production, where
connections come and go with every request.
"""

import sqlite3
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import session as db_session  # noqa: E402


def _foreign_keys_on(engine) -> int:
    with engine.connect() as con:
        return con.execute(text("PRAGMA foreign_keys")).fetchone()[0]


def test_the_running_engine_enforces_foreign_keys():
    assert _foreign_keys_on(db_session.engine) == 1, (
        "SQLite is not enforcing foreign keys: every ON DELETE in the schema is "
        "decorative and orphaned rows will accumulate again"
    )


def test_enforcement_holds_for_a_connection_opened_later():
    """The pragma is per connection, so setting it once at build time is useless."""
    assert _foreign_keys_on(db_session.engine) == 1
    # a brand new pool of connections, not a reused one
    db_session.engine.dispose()
    assert _foreign_keys_on(db_session.engine) == 1, (
        "a connection opened after the Engine was built has enforcement off"
    )


def test_an_orphaned_row_is_refused(tmp_path):
    """The point of the whole change."""
    url = f"sqlite:///{(tmp_path / 'enforced.db').as_posix()}"
    engine = db_session._make_engine(url)

    with engine.begin() as con:
        con.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        con.execute(text(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent (id) ON DELETE CASCADE)"))

    with pytest.raises(IntegrityError) as caught:
        with engine.begin() as con:
            con.execute(text("INSERT INTO child (parent_id) VALUES (99999)"))
    assert "FOREIGN KEY" in str(caught.value.orig), caught.value.orig

    engine.dispose()


def test_a_valid_row_is_still_accepted(tmp_path):
    """Enforcement that refuses everything is not enforcement."""
    url = f"sqlite:///{(tmp_path / 'valid.db').as_posix()}"
    engine = db_session._make_engine(url)

    with engine.begin() as con:
        con.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        con.execute(text("INSERT INTO parent VALUES (1)"))
        con.execute(text(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent (id) ON DELETE CASCADE)"))

    with engine.begin() as con:
        con.execute(text("INSERT INTO child (parent_id) VALUES (1)"))

    with engine.connect() as con:
        assert con.execute(text("SELECT count(*) FROM child")).fetchone()[0] == 1
    engine.dispose()


def test_the_declared_delete_actions_actually_happen(tmp_path):
    """The reason to want enforcement: CASCADE and SET NULL were never running.

    Without it, deleting a category left its spec definitions pointing at a row
    that no longer existed -- 53 of them on the live database.
    """
    url = f"sqlite:///{(tmp_path / 'actions.db').as_posix()}"
    engine = db_session._make_engine(url)

    with engine.begin() as con:
        con.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
        con.execute(text("INSERT INTO parent VALUES (1)"))
        con.execute(text(
            "CREATE TABLE cascaded (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent (id) ON DELETE CASCADE)"))
        con.execute(text(
            "CREATE TABLE kept (id INTEGER PRIMARY KEY, name TEXT, "
            "parent_id INTEGER REFERENCES parent (id) ON DELETE SET NULL)"))
        con.execute(text("INSERT INTO cascaded (parent_id) VALUES (1)"))
        con.execute(text("INSERT INTO kept (name, parent_id) VALUES ('اسم', 1)"))

        con.execute(text("DELETE FROM parent WHERE id = 1"))

        assert con.execute(text("SELECT count(*) FROM cascaded")).fetchone()[0] == 0
        name, parent_id = con.execute(
            text("SELECT name, parent_id FROM kept")).fetchone()
        assert (name, parent_id) == ("اسم", None), (
            f"SET NULL did not run: the row kept its dangling link ({name!r}, "
            f"{parent_id!r})"
        )

    engine.dispose()


def test_a_database_with_violations_would_be_caught_at_startup(tmp_path):
    """Why the cleanup had to come first.

    With enforcement on, an existing violation does not fail at startup on its
    own -- SQLite only refuses *new* writes. So this is not about detection; it
    is the reason a delete of a still-referenced parent now raises instead of
    quietly leaving the child behind.
    """
    db = tmp_path / "existing.db"
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        con.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, "
            "parent_id INTEGER REFERENCES parent (id) ON DELETE CASCADE)")
        con.execute("INSERT INTO child (parent_id) VALUES (99999)")
        con.commit()
    finally:
        con.close()

    engine = db_session._make_engine(f"sqlite:///{db.as_posix()}")
    with engine.begin() as con:
        violations = con.execute(text("PRAGMA foreign_key_check")).fetchall()
    assert len(violations) == 1, (
        "the violation is invisible to a connection with enforcement on -- which "
        "is why check_db_health.py has to be run as its own step"
    )
    engine.dispose()


def test_the_live_database_has_nothing_for_enforcement_to_trip_over():
    """The precondition: the cleanup ran before the pragma was turned on."""
    from scripts.check_db_health import check

    problems, _ = check(ROOT / "fleet_assets.db")
    assert not problems, (
        "enforcement is on but the live database still has violations, so any "
        f"write touching them will now fail: {problems}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))