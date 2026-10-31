import sqlite3

import pytest
from sqlalchemy import create_engine

from app.database.backup import backup_sqlite_database
from app.database import init_db as init_db_module


def test_sqlite_upgrade_backup_is_verified_and_can_restore_original_rows(tmp_path, monkeypatch):
    database_path = tmp_path / "user-data.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample (value) VALUES ('preserve me')")
    database_url = f"sqlite:///{database_path.as_posix()}"
    backup_path = backup_sqlite_database(database_url)
    assert backup_path is not None and backup_path.is_file()

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE sample SET value = 'damaged by failed migration'")
    monkeypatch.setattr(init_db_module.settings, "DATABASE_URL", database_url)
    monkeypatch.setattr(init_db_module, "engine", create_engine(database_url))

    def failed_upgrade():
        raise RuntimeError("synthetic migration failure")

    with pytest.raises(RuntimeError, match="synthetic migration failure"):
        init_db_module._run_with_database_backup(failed_upgrade, backup_path)

    with sqlite3.connect(database_path) as connection:
        value = connection.execute("SELECT value FROM sample").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert value == "preserve me"
    assert integrity == "ok"


def test_current_database_startup_does_not_run_data_cleanup(monkeypatch):
    class Inspector:
        @staticmethod
        def get_table_names():
            return ["alembic_version"]

    def unexpected(*_args, **_kwargs):
        pytest.fail("Routine startup must not normalize or delete operational data")

    monkeypatch.setattr(init_db_module, "inspect", lambda _engine: Inspector())
    monkeypatch.setattr(init_db_module, "_alembic_config", lambda: object())
    monkeypatch.setattr(init_db_module, "_alembic_upgrade_is_pending", lambda _config: False)
    monkeypatch.setattr(init_db_module, "_normalize_equipment_classification_defaults", unexpected)
    monkeypatch.setattr(init_db_module, "_repair_equipment_current_meters", unexpected)

    init_db_module.init_db()
