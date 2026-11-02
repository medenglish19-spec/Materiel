import importlib

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_driver_model_migration_backfills_assigned_equipment_and_preserves_rows(tmp_path):
    revision = importlib.import_module("migrations.versions.20261030_driver_model")
    database = tmp_path / "driver_model.db"
    scratch = create_engine(f"sqlite:///{database}")
    with scratch.begin() as connection:
        connection.execute(text("CREATE TABLE equipment_models (id INTEGER NOT NULL PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE equipment ("
                "id INTEGER NOT NULL PRIMARY KEY, equipment_model_id INTEGER)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE drivers ("
                "id INTEGER NOT NULL PRIMARY KEY, employee_number VARCHAR(50) NOT NULL, "
                "first_name VARCHAR(100) NOT NULL, last_name VARCHAR(100) NOT NULL, "
                "center VARCHAR(120), registration_number VARCHAR(80), "
                "license_class VARCHAR(50) NOT NULL, assigned_equipment_id INTEGER)"
            )
        )
        connection.execute(text("INSERT INTO equipment_models (id) VALUES (8)"))
        connection.execute(text("INSERT INTO equipment (id, equipment_model_id) VALUES (4, 8)"))
        connection.execute(
            text(
                "INSERT INTO drivers (id, employee_number, first_name, last_name, license_class, assigned_equipment_id) "
                "VALUES (1, 'DRV-1', 'سائق', 'سابق', 'B', 4)"
            )
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision.down_revision},
        )
    scratch.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, revision.revision)
    local = create_engine(f"sqlite:///{database}")
    with local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("drivers")}
        assert "equipment_model_id" in columns
        assert connection.execute(
            text("SELECT id, assigned_equipment_id, equipment_model_id FROM drivers")
        ).all() == [(1, 4, 8)]
        assert {
            foreign_key["name"] for foreign_key in inspect(connection).get_foreign_keys("drivers")
        } == {"fk_drivers_equipment_model_id_equipment_models"}
        assert "ix_drivers_equipment_model_id" in {
            index["name"] for index in inspect(connection).get_indexes("drivers")
        }
        assert connection.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
        ).scalar() == 0
    local.dispose()

    command.downgrade(config, revision.down_revision)
    local = create_engine(f"sqlite:///{database}")
    with local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("drivers")}
        assert "equipment_model_id" not in columns
        assert connection.execute(text("SELECT COUNT(*) FROM drivers")).scalar() == 1
    local.dispose()
