import importlib.util
from pathlib import Path

from alembic import command, op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


def _run_revision_file(path: Path, connection) -> None:
    spec = importlib.util.spec_from_file_location("legacy_revision_0007", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        module.upgrade()


def test_legacy_sqlite_database_upgrades_through_0014_without_losing_repair_data(tmp_path):
    database = tmp_path / "legacy-repairs.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_engine(database_url)

    with engine.begin() as connection:
        for table_name in ("users", "equipment", "maintenance_records", "equipment_types", "equipment_models"):
            connection.execute(text(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"))
        _run_revision_file(ROOT / "migrations/versions/0007_faults_repairs.py", connection)
        connection.execute(text("INSERT INTO users (id) VALUES (1)"))
        connection.execute(text("INSERT INTO equipment (id) VALUES (1)"))
        connection.execute(text("INSERT INTO faults (equipment_id, reported_date, description, created_at, updated_at) "
                                "VALUES (1, '2026-10-31', 'legacy fault', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO repairs (fault_id, repair_date, action_taken, created_at, created_by_id) "
                                "VALUES (1, '2026-10-31', 'legacy repair', CURRENT_TIMESTAMP, 1)"))
        connection.execute(text("INSERT INTO spare_parts (part_number, name) VALUES ('P-1', 'Legacy part')"))
        connection.execute(text("INSERT INTO repair_parts (repair_id, spare_part_id, quantity) VALUES (1, 1, 2)"))

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "0007_faults_repairs")
    command.upgrade(config, "0014_freeze_equipment_master_data")

    inspector = inspect(engine)
    repair_part_columns = {column["name"]: column for column in inspector.get_columns("repair_parts")}
    assert repair_part_columns["distribution_document"]["nullable"] is True
    repair_checks = {constraint["name"] for constraint in inspector.get_check_constraints("repairs")}
    assert "ck_repair_workshop_type" in repair_checks
    assert "ck_external_repair_requires_dispatch_document" in repair_checks
    assert "ck_fault_exploitation_impact" in {
        constraint["name"] for constraint in inspector.get_check_constraints("faults")
    }
    assert "is_frozen" in {column["name"] for column in inspector.get_columns("equipment_types")}
    assert "is_frozen" in {column["name"] for column in inspector.get_columns("equipment_models")}
    assert {column["name"] for column in inspector.get_columns("spare_parts")} >= {
        "receiving_document", "part_number", "name",
    }

    with engine.connect() as connection:
        assert connection.execute(text("SELECT description FROM faults WHERE id=1")).scalar_one() == "legacy fault"
        assert connection.execute(text("SELECT action_taken, workshop_type FROM repairs WHERE id=1")).one() == (
            "legacy repair", "internal",
        )
        assert connection.execute(text("SELECT quantity, distribution_document FROM repair_parts WHERE id=1")).one() == (
            2, None,
        )
        assert connection.execute(text("SELECT name, receiving_document FROM spare_parts WHERE id=1")).one() == (
            "Legacy part", None,
        )
    engine.dispose()
