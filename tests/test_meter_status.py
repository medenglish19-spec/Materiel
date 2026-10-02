from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType, EquipmentModel
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings import services

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_not_working_meter_status_is_saved_on_reading_and_repair_returns_to_working():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        et = EquipmentType(name="نوع اختبار الحالة", measurement_unit="km")
        db.add(et)
        db.flush()
        model = EquipmentModel(name="طراز اختبار الحالة", equipment_type_id=et.id)
        db.add(model)
        db.flush()
        equipment = Equipment(asset_code="STATUS-1", registration_number="688", equipment_type_id=et.id, equipment_model_id=model.id, operational_status="available")
        db.add(equipment)
        db.commit()
        db.refresh(equipment)

        first = services.create_reading(db, equipment.id, odometer=100, reading_date=datetime(2026, 8, 15), equipment_status="unavailable")
        assert equipment.operational_status == "available"
        assert first.equipment_status == "unavailable"

        second = services.create_reading(db, equipment.id, odometer=120, reading_date=datetime(2026, 8, 16), equipment_status="available")
        assert equipment.operational_status == "available"
        assert second.equipment_status == "available"

        saved = db.query(MeterReading).order_by(MeterReading.reading_date).all()
        assert [r.equipment_status for r in saved] == ["unavailable", "available"]
    finally:
        db.close()
