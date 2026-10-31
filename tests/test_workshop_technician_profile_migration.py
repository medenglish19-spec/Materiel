import importlib

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_workshop_technician_profile_migration_preserves_existing_rows(tmp_path):
    revision = importlib.import_module("migrations.versions.20261030_workshop_technician_profile")

    database = tmp_path / "technician_registration.db"
    scratch = create_engine(f"sqlite:///{database}")
    with scratch.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workshop_technicians ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "employee_number VARCHAR(50) NOT NULL, "
                "full_name VARCHAR(160) NOT NULL, "
                "specialization VARCHAR(120), "
                "is_active INTEGER NOT NULL DEFAULT 1, "
                "notes TEXT, "
                "CONSTRAINT uq_workshop_technician_employee_number UNIQUE (employee_number))"
            )
        )
        connection.execute(
            text("INSERT INTO workshop_technicians (id, employee_number, full_name) VALUES (1, 'TECH-1', 'فني سابق')")
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
        columns = {column["name"] for column in inspect(connection).get_columns("workshop_technicians")}
        assert {"professional_rank", "registration_number"} <= columns
        assert connection.execute(
            text("SELECT id, employee_number, full_name, professional_rank, registration_number FROM workshop_technicians")
        ).all() == [(1, "TECH-1", "فني سابق", None, None)]
        assert connection.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
        ).scalar() == 0
    local.dispose()

    command.downgrade(config, revision.down_revision)
    local = create_engine(f"sqlite:///{database}")
    with local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("workshop_technicians")}
        assert not {"professional_rank", "registration_number"} & columns
        assert connection.execute(text("SELECT COUNT(*) FROM workshop_technicians")).scalar() == 1
    local.dispose()
