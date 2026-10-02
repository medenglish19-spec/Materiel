from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.router import meter_reading_create, meter_readings_bulk_create, meter_readings_import_excel
from app.modules.meter_readings import services
from app.modules.users.models import User


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def seed(db, registration, unit="km"):
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


def user(db, name="input-matrix"):
    value = User(username=name, full_name="اختبار الإدخال", hashed_password="x", role="admin")
    db.add(value)
    db.commit()
    db.refresh(value)
    return value


def test_manual_option_multiple_numeric_formats_and_retry_after_error(db):
    equipment = seed(db, "M-100", "km")
    actor = user(db, "manual-matrix")

    response = meter_reading_create(
        equipment_id=equipment.id,
        reading_date="15/08/2026",
        value="1,234.5",
        equipment_status="لا يعمل",
        notes="اختبار يدوي",
        db=db,
        current_user=actor,
    )
    assert response.status_code == 200
    assert float(db.query(MeterReading).one().odometer) == 1234.5
    assert equipment.operational_status == "available"

    with pytest.raises(HTTPException) as exc:
        meter_reading_create(
            equipment_id=equipment.id,
            reading_date="16/08/2026",
            value="1,200",
            equipment_status="يعمل",
            notes="محاولة خاطئة",
            db=db,
            current_user=actor,
        )
    assert exc.value.status_code == 400
    assert "طراز-M-100" in str(exc.value.detail)
    assert "M-100" in str(exc.value.detail)
    assert "أقل من القراءة المسجلة" in str(exc.value.detail)
    assert db.query(MeterReading).count() == 1

    response = meter_reading_create(
        equipment_id=equipment.id,
        reading_date="16/08/2026",
        value="1,250.7",
        equipment_status="يعمل",
        notes="بعد التصحيح",
        db=db,
        current_user=actor,
    )
    assert response.status_code == 200
    assert db.query(MeterReading).count() == 2
    assert float(db.query(MeterReading).order_by(MeterReading.reading_date.desc()).first().odometer) == 1250.7
    assert equipment.operational_status == "available"


def test_manual_hours_accepts_integer_decimal_and_arabic_digits(db):
    equipment = seed(db, "H-200", "hours")
    actor = user(db, "hours-matrix")
    for reading_date, value in [
        ("15/08/2026", "100"),
        ("16/08/2026", "125.5"),
        ("17/08/2026", "١٥٠٫٧"),
    ]:
        response = meter_reading_create(
            equipment_id=equipment.id,
            reading_date=reading_date,
            value=value,
            equipment_status="متاح",
            notes="صيغة اختبار",
            db=db,
            current_user=actor,
        )
        assert response.status_code == 200
    saved = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).order_by(MeterReading.reading_date).all()
    assert [float(x.hours) for x in saved] == [100.0, 125.5, 150.7]


def test_paste_option_accepts_date_number_formats_and_status_aliases_then_retries(db):
    equipment = seed(db, "P-300", "km")
    actor = user(db, "paste-matrix")
    services.create_reading(db, equipment.id, odometer=100, reading_date=datetime(2026, 8, 14))

    bad_payload = {
        "rows": [{
            "equipment_type": "نوع-P-300",
            "registration": "P-300",
            "reading_date": "15/08/2026",
            "km_value": "٩٠٫٥",
            "hours_value": None,
            "equipment_status": "لا يعمل",
            "_row_number": 1,
        }]
    }
    response = meter_readings_bulk_create(bad_payload, db=db, current_user=actor)
    payload = response.body.decode("utf-8")
    assert response.status_code == 200
    assert '"created":0' in payload
    assert '"skipped":1' in payload
    assert "P-300" in payload
    assert "طراز-P-300" in payload
    assert "أقل من القراءة المسجلة" in payload
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 1

    corrected_payload = {
        "rows": [{
            "equipment_type": "نوع-P-300",
            "registration": "P-300",
            "reading_date": "16-08-2026",
            "km_value": "1,050.2",
            "hours_value": None,
            "equipment_status": "working",
            "_row_number": 1,
        }]
    }
    response = meter_readings_bulk_create(corrected_payload, db=db, current_user=actor)
    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert '"created":1' in payload
    assert '"skipped":0' in payload
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 2
    assert equipment.operational_status == "available"


def make_excel(rows, headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def test_excel_option_accepts_arabic_english_headers_reordered_dates_and_values(db):
    equipment_km = seed(db, "E-400", "km")
    equipment_hours = seed(db, "E-401", "hours")
    actor = user(db, "excel-matrix")
    headers = ["Status", "رقم التسجيل", "Date", "الطراز", "Odometer", "Hour meter"]
    rows = [
        ["working", "E-400", date(2026, 8, 15), "طراز-E-400", "2,000.5", None],
        ["لا يعمل", "E-401", 46250, "طراز-E-401", None, "٧٥٫٢"],
        ["available", "E-400", "17/08/2026", "طراز-E-400", "2,100", None],
    ]
    buffer = make_excel(rows, headers)
    response = meter_readings_import_excel(UploadFile(filename="matrix.xlsx", file=buffer), None, db, actor)
    assert response.status_code == 200
    payload = response.body.decode("utf-8")
    assert '"created":3' in payload
    assert '"skipped":0' in payload
    km_values = [float(x.odometer) for x in db.query(MeterReading).filter(MeterReading.equipment_id == equipment_km.id).order_by(MeterReading.reading_date)]
    hour_values = [float(x.hours) for x in db.query(MeterReading).filter(MeterReading.equipment_id == equipment_hours.id).order_by(MeterReading.reading_date)]
    assert km_values == [2000.5, 2100.0]
    assert hour_values == [75.2]
    assert equipment_km.operational_status == "available"
    assert equipment_hours.operational_status == "available"\n    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment_hours.id).one().equipment_status == "unavailable"


def test_excel_error_identifies_equipment_and_retry_with_corrected_file(db):
    equipment = seed(db, "E-500", "km")
    actor = user(db, "excel-retry")
    services.create_reading(db, equipment.id, odometer=500, reading_date=datetime(2026, 8, 14))

    bad = make_excel(
        [["E-500", "طراز-E-500", "15/08/2026", 450, None, "يعمل"]],
        ["رقم التسجيل", "الطراز", "التاريخ", "الكيلومترات", "الساعات", "حالة العداد"],
    )
    response = meter_readings_import_excel(UploadFile(filename="bad.xlsx", file=bad), None, db, actor)
    payload = response.body.decode("utf-8")
    assert response.status_code == 200
    assert '"created":0' in payload
    assert '"skipped":1' in payload
    assert "E-500" in payload
    assert "طراز-E-500" in payload
    assert "أقل من القراءة المسجلة" in payload
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 1

    good = make_excel(
        [["E-500", "طراز-E-500", "16/08/2026", "٥٥٠٫٧", None, "working"]],
        ["رقم التسجيل", "الطراز", "التاريخ", "الكيلومترات", "الساعات", "حالة العداد"],
    )
    response = meter_readings_import_excel(UploadFile(filename="corrected.xlsx", file=good), None, db, actor)
    payload = response.body.decode("utf-8")
    assert response.status_code == 200
    assert '"created":1' in payload
    assert '"skipped":0' in payload
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 2
    latest = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).order_by(MeterReading.reading_date.desc()).first()
    assert float(latest.odometer) == 550.7
