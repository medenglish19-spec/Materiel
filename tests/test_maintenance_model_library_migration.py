"""Upgrade and downgrade coverage for the separate model operation library."""

from sqlalchemy import create_engine, inspect, text


def test_model_library_migration_moves_legacy_rows_and_reverses_them(tmp_path):
    from importlib import import_module

    from alembic import command
    from alembic.config import Config

    revision = import_module("migrations.versions.20261023_maintenance_model_scoped_operations")

    database = tmp_path / "maintenance_model_library.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision.down_revision},
        )
        connection.execute(text("CREATE TABLE equipment_models (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE maintenance_operation_groups (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE equipment (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE maintenance_operations ("
            "id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, interval_km NUMERIC(10,1), "
            "interval_hours NUMERIC(10,1), interval_days INTEGER, warning_km NUMERIC(10,1), "
            "warning_days INTEGER, is_active BOOLEAN NOT NULL DEFAULT 1, description TEXT, group_id INTEGER, "
            "scope_model_id INTEGER, CONSTRAINT fk_maintenance_operations_scope_model "
            "FOREIGN KEY(scope_model_id) REFERENCES equipment_models(id))"
        ))
        connection.execute(text(
            "CREATE TABLE maintenance_operation_models ("
            "operation_id INTEGER NOT NULL, equipment_model_id INTEGER NOT NULL, condition_source VARCHAR(20), "
            "interval_km NUMERIC(10,1), interval_hours NUMERIC(10,1), interval_days INTEGER, "
            "is_active BOOLEAN NOT NULL DEFAULT 1, PRIMARY KEY(operation_id, equipment_model_id))"
        ))
        connection.execute(text("CREATE INDEX ix_maintenance_operations_scope_model_id ON maintenance_operations(scope_model_id)"))
        connection.execute(text("CREATE TABLE maintenance_plans (id INTEGER PRIMARY KEY, equipment_model_id INTEGER NOT NULL)"))
        connection.execute(text(
            "CREATE TABLE maintenance_plan_operations ("
            "id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, operation_id INTEGER NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, "
            "CONSTRAINT uq_maintenance_plan_operation UNIQUE(plan_id, operation_id), "
            "CONSTRAINT fk_maintenance_plan_operations_operation FOREIGN KEY(operation_id) REFERENCES maintenance_operations(id))"
        ))
        connection.execute(text(
            "CREATE TABLE maintenance_records ("
            "id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL, operation_id INTEGER, plan_id INTEGER, "
            "maintenance_date DATE NOT NULL, CONSTRAINT fk_maintenance_records_operation "
            "FOREIGN KEY(operation_id) REFERENCES maintenance_operations(id))"
        ))
        connection.execute(text("INSERT INTO equipment_models (id) VALUES (1)"))
        connection.execute(text("INSERT INTO maintenance_operation_groups (id) VALUES (1)"))
        connection.execute(text(
            "INSERT INTO maintenance_operations (id, name, group_id, warning_km, scope_model_id) "
            "VALUES (1, 'عملية عامة', 1, 100, NULL), (2, 'عملية خاصة قديمة', 1, 250, 1)"
        ))
        connection.execute(text(
            "INSERT INTO maintenance_operation_models "
            "(operation_id, equipment_model_id, condition_source, interval_km, is_active) "
            "VALUES (1, 1, 'model', 5000, 1), (2, 1, 'model', 15000, 1)"
        ))
        connection.execute(text("INSERT INTO maintenance_plans (id, equipment_model_id) VALUES (1, 1)"))
        connection.execute(text("INSERT INTO maintenance_plan_operations (id, plan_id, operation_id) VALUES (1, 1, 2)"))
        connection.execute(text(
            "INSERT INTO maintenance_records (id, equipment_id, operation_id, plan_id, maintenance_date) "
            "VALUES (1, 1, 2, 1, '2026-01-01')"
        ))
    engine.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, revision.revision)

    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        general_columns = {column["name"] for column in inspect(connection).get_columns("maintenance_operations")}
        assert "scope_model_id" not in general_columns
        private = connection.execute(text(
            "SELECT id, equipment_model_id, name, interval_km, warning_km FROM maintenance_model_operations"
        )).one()
        assert private == (2, 1, "عملية خاصة قديمة", 15000, 250)
        assert connection.execute(text(
            "SELECT operation_id, model_operation_id FROM maintenance_plan_operations"
        )).all() == [(None, 2)]
        assert connection.execute(text(
            "SELECT operation_id, model_operation_id FROM maintenance_records"
        )).all() == [(None, 2)]
        assert connection.execute(text(
            "SELECT COUNT(*) FROM maintenance_operation_models WHERE operation_id=2"
        )).scalar_one() == 0
    engine.dispose()

    command.downgrade(config, revision.down_revision)
    engine = create_engine(f"sqlite:///{database}")
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT id, name, scope_model_id FROM maintenance_operations WHERE id=2"
        )).one()
        assert row == (2, "عملية خاصة قديمة", 1)
        assert connection.execute(text(
            "SELECT operation_id FROM maintenance_plan_operations"
        )).all() == [(2,)]
        assert connection.execute(text(
            "SELECT operation_id FROM maintenance_records"
        )).all() == [(2,)]
        assert connection.execute(text(
            "SELECT interval_km FROM maintenance_operation_models WHERE operation_id=2 AND equipment_model_id=1"
        )).scalar_one() == 15000
    engine.dispose()
