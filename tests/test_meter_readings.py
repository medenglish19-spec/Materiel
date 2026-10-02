from datetime import datetime, timezone, timedelta
from io import BytesIO

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.meter_readings import services
from app.modules.meter_readings.audit import MeterReadingOperation, MeterReadingOperationEvent, MeterReadingChange
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.router import meter_readings_import_excel
from app.modules.users.models import User

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def seed_equipment(db, registration="688", unit="km"):
    et = EquipmentType(name=f"نوع-{registration}", measurement_unit=unit)
    db.add(et)
    db.flush()
    model = EquipmentModel(name=f"طراز-{registration}", equipment_type_id=et.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code=f"A-{registration}",
        registration_number=registration,
        equipment_type_id=et.id,
        equipment_model_id=model.id,
        operational_status="available",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def bulk_row(equipment, reading_date, value, status="available", row_number=2):
    return {
        "equipment_type": equipment.equipment_type.name,
        "registration": equipment.registration_number,
        "reading_date": reading_date,
        "km_value": value,
        "hours_value": None,
        "equipment_status": status,
        "_row_number": row_number,
    }


def test_manual_reading_and_monotonic_validation(db):
    equipment = seed_equipment(db)
    base = datetime(2026, 8, 10)
    first = services.create_reading(db, equipment.id, odometer=100, reading_date=base, equipment_status="available")
    assert first.odometer == 100
    second = services.create_reading(db, equipment.id, odometer=120, reading_date=base + timedelta(days=1), equipment_status="unavailable")
    assert second.odometer == 120
    assert equipment.operational_status == "available"
    with pytest.raises(ValueError, match="أقل من القراءة المسجلة"):
        services.create_reading(db, equipment.id, odometer=110, reading_date=base + timedelta(days=2))
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 2
    with pytest.raises(ValueError, match="أكبر من القراءة اللاحقة"):
        services.create_reading(db, equipment.id, odometer=130, reading_date=base - timedelta(days=1))
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 2
    with pytest.raises(ValueError, match="تاريخ مستقبلي"):
        services.create_reading(db, equipment.id, odometer=125, reading_date=datetime.now(timezone.utc) + timedelta(days=1))
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 2


def test_duplicate_manual_reading_same_date_and_value_is_rejected(db):
    equipment = seed_equipment(db, "DUP-1", "km")
    reading_date = datetime(2026, 8, 17)
    services.create_reading(db, equipment.id, odometer=500, reading_date=reading_date)
    with pytest.raises(ValueError, match="مكررة|مكرر"):
        services.create_reading(db, equipment.id, odometer=500, reading_date=reading_date)
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 1


def test_duplicate_bulk_reading_same_date_and_value_is_rejected(db):
    equipment = seed_equipment(db, "DUP-2", "km")
    reading_date = datetime(2026, 8, 17)
    services.create_reading(db, equipment.id, odometer=700, reading_date=reading_date)
    created, rejected, errors, warnings, reading_ids = services.create_bulk_readings(
        db, [bulk_row(equipment, reading_date, 700, row_number=2)]
    )
    assert created == 0
    assert rejected == 1
    assert not reading_ids
    assert any("مكررة" in error for error in errors)
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 1


def test_meter_change_history_records_old_and_new_values(db):
    equipment = seed_equipment(db, "356", "km")
    reading = services.create_reading(db, equipment.id, odometer=100, reading_date=datetime(2026, 8, 10))
    db.query(MeterReadingChange).filter(MeterReadingChange.reading_id == reading.id).delete(synchronize_session=False)
    db.flush()

    reading.odometer = 120
    db.commit()

    change = (
        db.query(MeterReadingChange)
        .filter(MeterReadingChange.reading_id == reading.id, MeterReadingChange.action == "update")
        .order_by(MeterReadingChange.id.desc())
        .first()
    )
    assert change is not None
    assert float(change.old_value) == 100.0
    assert float(change.new_value) == 120.0
    assert change.unit == "km"
    assert change.equipment_id == equipment.id
    assert change.reading_date == reading.reading_date


def test_bulk_import_saves_valid_rows_skips_invalid_rows_and_blank_is_zero(db):
    equipment = seed_equipment(db, "688")
    base = datetime(2026, 8, 10)
    services.create_reading(db, equipment.id, odometer=100, reading_date=base)
    rows = [
        bulk_row(equipment, base + timedelta(days=1), 120, row_number=2),
        bulk_row(equipment, base + timedelta(days=2), 110, row_number=3),
        bulk_row(equipment, base + timedelta(days=3), None, status="unavailable", row_number=4),
    ]
    created, rejected, errors, warnings, reading_ids = services.create_bulk_readings(db, rows)
    assert created == 2
    assert rejected == 1
    assert len(reading_ids) == 2
    assert any("أقل من القراءة المسجلة" in e for e in errors)
    assert any("تم اعتبار القراءة صفرًا" in w for w in warnings)
    saved = db.query(MeterReading).filter(MeterReading.id.in_(reading_ids)).order_by(MeterReading.reading_date).all()
    assert [float(x.odometer) for x in saved] == [120.0, 0.0]
    assert saved[-1].equipment_status == "unavailable"
    assert equipment.operational_status == "available"


def test_excel_arabic_headers_reverse_order_invalid_row_and_operation_log(db):
    equipment = seed_equipment(db, "688")
    wb = Workbook()
    ws = wb.active
    ws.append(["حالة العداد", "الكيلومترات", "التاريخ", "رقم التسجيل", "نوع العتاد", "الساعات"])
    ws.append(["يعمل", 333, "15/08/2026", "688", "نوع-688", None])
    ws.append(["لا يعمل", None, "16/08/2026", "688", "نوع-688", None])
    ws.append(["يعمل", 200, "17/08/2026", "688", "نوع-688", None])
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    upload = UploadFile(filename="قراءات-عربية.xlsx", file=buffer)
    user = User(username="tester", full_name="مختبر", hashed_password="x", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)

    response = meter_readings_import_excel(upload, None, db, user)
    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert '"created":2' in payload
    assert '"skipped":1' in payload
    assert "تم اعتبار القراءة صفرًا" in payload

    readings = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).order_by(MeterReading.reading_date).all()
    assert len(readings) == 2
    assert [float(x.odometer) for x in readings] == [333.0, 0.0]
    assert readings[-1].equipment_status == "unavailable"
    assert equipment.operational_status == "available"

    operation = db.query(MeterReadingOperation).one()
    assert operation.kind == "excel"
    assert operation.filename == "قراءات-عربية.xlsx"
    assert operation.total_rows == 3
    assert operation.accepted_rows == 2
    assert operation.rejected_rows == 1
    assert len(operation.reading_ids) == 2
    events = db.query(MeterReadingOperationEvent).filter(MeterReadingOperationEvent.operation_id == operation.id).all()
    validation_event = next(e for e in events if e.event_type == "validation_errors")
    assert validation_event.payload["errors"]
    assert any("الصف" in str(e) for e in validation_event.payload["errors"])
    warning_event = next(e for e in events if e.event_type == "warnings")
    assert any("تم اعتبار القراءة صفرًا" in str(w) for w in warning_event.payload["warnings"])


def test_operation_rollback_removes_only_its_readings(db):
    equipment = seed_equipment(db, "688")
    base = datetime(2026, 8, 10)
    permanent = services.create_reading(db, equipment.id, odometer=100, reading_date=base)
    created, rejected, errors, warnings, ids = services.create_bulk_readings(db, [bulk_row(equipment, base + timedelta(days=1), 120)])
    assert created == 1 and not errors
    from app.modules.meter_readings.audit_service import create_operation, rollback_operation
    op = create_operation(db, "paste", user_id=None, total_rows=1, reading_ids=ids, rejected_rows=0)
    db.commit()
    removed = rollback_operation(db, op, None)
    assert removed == 1
    assert db.query(MeterReading).filter(MeterReading.id == permanent.id).count() == 1
    assert db.query(MeterReading).filter(MeterReading.id.in_(ids)).count() == 0
    assert op.status == "rolled_back"


def test_excel_headers_are_detected_without_relying_on_column_order(db):
    equipment = seed_equipment(db, "688", "km")
    wb = Workbook()
    ws = wb.active
    ws.append(["رقم التسجيل", "حالة العداد", "عداد الكم", "نوع العتاد", "التاريخ", "عداد الساعات"])
    ws.append(["688", "يعمل", 900, "نوع-688", "16/08/2026", None])
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    upload = UploadFile(filename="headers.xlsx", file=buffer)
    user = User(username="headers-tester", full_name="اختبار العناوين", hashed_password="x", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    response = meter_readings_import_excel(upload, None, db, user)
    assert response.status_code == 200
    assert b'"created":1' in response.body
    reading = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).one()
    assert float(reading.odometer) == 900.0
    assert reading.equipment_status == "available"
