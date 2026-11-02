import sqlite3
from pathlib import Path

import pytest

from scripts.backup_shared_database import backup_database


def test_backup_is_a_consistent_restorable_snapshot(tmp_path: Path):
    source = tmp_path / "shared.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE equipment (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO equipment (name) VALUES ('loader')")

    snapshot = backup_database(source, tmp_path / "backups")

    assert snapshot.is_file()
    with sqlite3.connect(snapshot) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("SELECT id, name FROM equipment").fetchall() == [(1, "loader")]


def test_missing_database_does_not_create_a_backup(tmp_path: Path):
    backup_dir = tmp_path / "backups"

    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "missing.db", backup_dir)

    assert not backup_dir.exists()
