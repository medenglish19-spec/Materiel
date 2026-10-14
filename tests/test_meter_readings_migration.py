"""End-to-end checks for central meter ledger schema migration and DB guards."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.base import Base
from app.database import model_registry  # noqa: F401
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType


def test_migration_removes_local_values_backfills_and_guards_raw_writes():
    database = Path.cwd() / f".meter-ledger-migration-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        equipment_type = EquipmentType(name="Migration km", measurement_unit="km")
        session.add(equipment_type)
        session.flush()
        model = EquipmentModel(name="Migration model", equipment_type_id=equipment_type.id)
        session.add(model)
        session.flush()
        equipment = Equipment(
            asset_code="MIGRATION-1", registration_number="MIGRATION-1",
            equipment_type_id=equipment_type.id, equipment_model_id=model.id,
            operational_status="available",
        )
        session.add(equipment)
        session.commit()
        equipment_id = equipment.id
        second_equipment = Equipment(
            asset_code="MIGRATION-2", registration_number="MIGRATION-2",
            equipment_type_id=equipment_type.id, equipment_model_id=model.id,
            operational_status="available",
        )
        session.add(second_equipment)
        session.commit()
        second_equipment_id = second_equipment.id
    # Recreate the relevant pre-centralization schema on this disposable DB.
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_meter_readings_source_reference"))
        connection.execute(text("ALTER TABLE meter_readings DROP COLUMN source_reference"))
        for table, column in (
            ("fuel_records", "meter_value"), ("faults", "meter_value"),
            ("repairs", "meter_value"), ("maintenance_records", "meter_value"),
            ("missions", "departure_meter"), ("missions", "return_meter"),
            ("tire_movements", "meter_value"), ("battery_movements", "meter_value"),
        ):
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} NUMERIC(10,1)"))
        connection.execute(text("ALTER TABLE repairs DROP COLUMN updated_at"))
        connection.execute(text("ALTER TABLE maintenance_records DROP COLUMN updated_at"))
        connection.execute(text("""
            INSERT INTO fuel_records
              (equipment_id, fueling_date, sequence_number, quantity, meter_value, created_at, updated_at)
            VALUES (:equipment_id, '2026-10-01', 1, 20, 1234, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {"equipment_id": equipment_id})
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ('remove_closed_fault_status_20261013')"
        ))
    engine.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")

    migrated = create_engine(f"sqlite:///{database}")
    with migrated.connect() as connection:
        assert "meter_value" not in {c["name"] for c in inspect(connection).get_columns("fuel_records")}
        reading = connection.execute(text(
            "SELECT odometer, source, source_reference FROM meter_readings WHERE equipment_id=:id"
        ), {"id": equipment_id}).one()
        assert reading == (Decimal("1234.0"), "fuel", "fuel:1:meter")
        assert connection.execute(text(
            "SELECT current_odometer FROM equipment WHERE id=:id"), {"id": equipment_id}
        ).scalar_one() == Decimal("1234.0")

    with migrated.begin() as connection:
        connection.execute(text("""
            INSERT INTO meter_readings
              (equipment_id, reading_date, odometer, hours, source, equipment_status, created_at, updated_at)
            VALUES (:id, '2026-10-02 00:00:00', 1240, NULL, 'manual', 'available', :now, :now)
        """), {"id": equipment_id, "now": datetime.now()})
    with migrated.connect() as connection:
        assert connection.execute(text(
            "SELECT current_odometer FROM equipment WHERE id=:id"), {"id": equipment_id}
        ).scalar_one() == Decimal("1240.0")

    with migrated.begin() as connection:
        connection.execute(text(
            "UPDATE meter_readings SET equipment_id=:target WHERE equipment_id=:source AND odometer=1240"
        ), {"target": second_equipment_id, "source": equipment_id})
    with migrated.connect() as connection:
        assert connection.execute(text(
            "SELECT current_odometer FROM equipment WHERE id=:id"), {"id": equipment_id}
        ).scalar_one() == Decimal("1234.0")
        assert connection.execute(text(
            "SELECT current_odometer FROM equipment WHERE id=:id"), {"id": second_equipment_id}
        ).scalar_one() == Decimal("1240.0")

    with pytest.raises(IntegrityError, match="تسلسل قراءة العداد"):
        with migrated.begin() as connection:
            connection.execute(text("""
                INSERT INTO meter_readings
                  (equipment_id, reading_date, odometer, hours, source, equipment_status, created_at, updated_at)
                VALUES (:id, '2026-10-03 00:00:00', 1230, NULL, 'manual', 'available', :now, :now)
            """), {"id": equipment_id, "now": datetime.now()})
    migrated.dispose()
    database.unlink(missing_ok=True)
