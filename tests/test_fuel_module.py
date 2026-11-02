from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.fuel.models import FuelRecord
from app.modules.fuel.services import (
    ABNORMAL_FACTOR,
    add_record,
    distance_from_previous,
    enrich_records,
    list_records,
)


def test_fuel_model_and_abnormal_threshold():
    assert FuelRecord.__tablename__ == "fuel_records"
    assert ABNORMAL_FACTOR == Decimal("1.20")


def test_fuel_history_uses_chronological_meters_and_flags_abnormal_consumption():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        equipment_type = EquipmentType(name="Fuel test", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="Fuel test model", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()
        equipment = Equipment(
            asset_code="FUEL-TEST",
            registration_number="FUEL-TEST",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model.id,
            operational_status="available",
        )
        db.add(equipment)
        db.commit()

        today = date.today()
        for days_ago, meter, quantity in ((3, 1000, 20), (2, 2000, 20), (1, 3000, 80)):
            add_record(db, {
                "equipment_id": equipment.id,
                "fueling_date": today - timedelta(days=days_ago),
                "sequence_number": None,
                "meter_value": Decimal(meter),
                "quantity": Decimal(quantity),
            })

        records = list_records(db)
        enriched, averages = enrich_records(db, records)

        assert distance_from_previous(db, records[0]) == Decimal("1000")
        assert distance_from_previous(db, records[1]) == Decimal("1000")
        assert distance_from_previous(db, records[2]) is None
        assert [item["consumption"] for item in enriched] == [
            Decimal("8.00"),
            Decimal("2.00"),
            None,
        ]
        assert [item["meter_value"] for item in enriched] == [
            Decimal("3000.0"),
            Decimal("2000.0"),
            Decimal("1000.0"),
        ]
        assert averages[equipment.id] == Decimal("5.00")
        assert [item["abnormal"] for item in enriched] == [True, False, False]
    finally:
        db.close()
        engine.dispose()
