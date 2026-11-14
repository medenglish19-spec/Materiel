import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20261022_missions_drivers.py"
)
SPEC = importlib.util.spec_from_file_location("missions_drivers_migration", MIGRATION_PATH)
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def test_missions_drivers_migration_creates_driver_schema_and_can_downgrade():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE equipment (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE missions (id INTEGER PRIMARY KEY)"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            MIGRATION.upgrade()

        inspector = inspect(connection)
        assert {
            "id",
            "employee_number",
            "first_name",
            "last_name",
            "center",
            "license_class",
            "license_issue_date",
            "license_expiry_date",
            "assigned_equipment_id",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
            "created_by_id",
            "updated_by_id",
        } == {column["name"] for column in inspector.get_columns("drivers")}
        assert "center_column_label" in {
            column["name"] for column in inspector.get_columns("driver_system_settings")
        }
        assert {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("drivers")
        } == {
            "fk_drivers_assigned_equipment_id_equipment",
            "fk_drivers_created_by_id_users",
            "fk_drivers_updated_by_id_users",
        }
        assert "driver_id" in {
            column["name"] for column in inspector.get_columns("missions")
        }
        assert {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("missions")
        } == {"fk_missions_driver_id_drivers"}
        assert {
            index["name"] for index in inspector.get_indexes("missions")
        } == {"ix_missions_driver_id"}

        with Operations.context(context):
            MIGRATION.downgrade()
        assert "drivers" not in inspect(connection).get_table_names()
        assert "driver_system_settings" not in inspect(connection).get_table_names()
        assert "driver_id" not in {
            column["name"] for column in inspect(connection).get_columns("missions")
        }

    engine.dispose()
