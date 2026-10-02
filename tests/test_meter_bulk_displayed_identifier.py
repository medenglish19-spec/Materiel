from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.router import meter_readings_bulk_create
from app.modules.users.models import User


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_bulk_paste_uses_asset_code_when_the_ui_displays_it_as_registration():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        meter_type = EquipmentType(name="مولد", measurement_unit="km")
        db.add(meter_type)
        db.flush()
        model = EquipmentModel(name="أزبيس", equipment_type_id=meter_type.id)
        db.add(model)
        db.flush()
        equipment = Equipment(
            asset_code="688",
            registration_number=None,
            equipment_type_id=meter_type.id,
            equipment_model_id=model.id,
            operational_status="available",
        )
        actor = User(username="paste-688", full_name="اختبار", hashed_password="x", role="admin")
        db.add_all([equipment, actor])
        db.commit()

        response = meter_readings_bulk_create(
            {
                "rows": [
                    {
                        "model": "أزبيس",
                        "registration": "688",
                        "reading_date": "13/08/2026",
                        "km_value": "999",
                        "hours_value": "",
                        "equipment_status": "لا يعمل",
                        "_row_number": 1,
                    }
                ]
            },
            db=db,
            current_user=actor,
        )

        body = response.body.decode("utf-8")
        assert response.status_code == 200
        assert '"created":1' in body
        assert '"skipped":0' in body
        saved = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).one()
        assert float(saved.odometer) == 999
        assert equipment.operational_status == "available"\n        assert saved.equipment_status == "unavailable"
    finally:
        db.close()
