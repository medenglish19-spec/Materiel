import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


_PREVIOUS_REVISION = "20261023_maintenance_model_scoped_operations"
_REVISION = "20261024_maintenance_operation_warning_hours"
_TABLES = ("maintenance_operations", "maintenance_model_operations")


def _database(tmp_path, name, *, warning_hours=False):
    database = tmp_path / name
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": _PREVIOUS_REVISION},
        )
        for table in _TABLES:
            column = ", warning_hours NUMERIC(10,1)" if warning_hours else ""
            constraint = ""
            if warning_hours:
                constraint_name = (
                    "ck_maintenance_model_operation_warning_hours_nonnegative"
                    if table == "maintenance_model_operations"
                    else "ck_maintenance_operation_warning_hours_nonnegative"
                )
                constraint = f", CONSTRAINT {constraint_name} CHECK (warning_hours IS NULL OR warning_hours >= 0)"
            connection.execute(text(
                f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, warning_km NUMERIC(10,1), "
                f"warning_days INTEGER{column}{constraint})"
            ))
            connection.execute(text(
                f"INSERT INTO {table} (id, warning_km, warning_days) VALUES (1, 100, 7)"
            ))
    engine.dispose()
    return database


def _upgrade(database):
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, _REVISION)


def test_warning_hours_migration_adds_column_and_preserves_existing_values(tmp_path):
    database = _database(tmp_path, "warning_hours.db")
    _upgrade(database)
    _upgrade(database)

    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        for table in _TABLES:
            columns = {column["name"] for column in inspect(connection).get_columns(table)}
            assert "warning_hours" in columns
            row = connection.execute(text(
                f"SELECT warning_km, warning_days, warning_hours FROM {table} WHERE id=1"
            )).one()
            assert row == (100, 7, None)
        with pytest.raises(IntegrityError):
            connection.execute(text(
                "INSERT INTO maintenance_operations (id, warning_hours) VALUES (2, -1)"
            ))
    engine.dispose()


def test_warning_hours_migration_accepts_columns_created_by_current_metadata(tmp_path):
    database = _database(tmp_path, "warning_hours_existing.db", warning_hours=True)
    _upgrade(database)

    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        assert all(
            "warning_hours" in {column["name"] for column in inspect(connection).get_columns(table)}
            for table in _TABLES
        )
        assert connection.execute(text(
            "SELECT warning_km, warning_days, warning_hours FROM maintenance_operations WHERE id=1"
        )).one() == (100, 7, None)
    engine.dispose()
