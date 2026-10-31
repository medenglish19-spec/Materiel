from datetime import datetime, timezone, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database import model_registry  # noqa: F401 - register cross-module meter listeners
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.meter_readings import services
from app.modules.meter_readings.audit import MeterReadingOperation, MeterReadingOperationEvent, MeterReadingChange
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.router import meter_readings_import_excel
from app.modules.fuel.models import FuelRecord
from app.modules.fuel.services import add_record as add_fuel_record, validate_record as validate_fuel_record
from app.modules.missions.services import add_mission
from app.modules.tires.models import Tire, TireMovement
from app.modules.batteries.models import Battery, BatteryMovement
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


@pytest.mark.parametrize(
    ("meter_value", "message"),
    [(Decimal("500"), "مكررة"), (Decimal("490"), "تعارض قراءة العداد")],
)
def test_maintenance_record_meter_uses_central_same_day_validation(db, meter_value, message):
    """صيانة وقراءة أخرى لا تسجلان قياسين متعارضين في اليوم نفسه."""
    from app.modules.maintenance.models import MaintenanceOperation, MaintenanceRecord

    equipment = seed_equipment(db, "MAINT-DUP", "km")
    operation = MaintenanceOperation(name="عملية اختبار", is_active=True)
    db.add(operation)
    db.flush()
    reading_date = datetime(2026, 8, 17)
    services.create_reading(db, equipment.id, odometer=500, reading_date=reading_date)

    db.add(MaintenanceRecord(
        equipment_id=equipment.id,
        operation_id=operation.id,
        maintenance_date=reading_date.date(),
        meter_value=meter_value,
        status="completed",
    ))
    with pytest.raises(ValueError, match=message):
        db.commit()
    db.rollback()

    assert db.query(MaintenanceRecord).count() == 0
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == 1


def test_direct_ledger_insert_rejects_a_value_above_a_later_reading(db):
    equipment = seed_equipment(db, "DIRECT-SEQ", "km")
    services.create_reading(db, equipment.id, odometer=120, reading_date=datetime(2026, 8, 20))
    db.add(MeterReading(
        equipment_id=equipment.id,
        reading_date=datetime(2026, 8, 19),
        odometer=130,
        source="manual",
        equipment_status="available",
    ))
    with pytest.raises(ValueError, match="أكبر من قراءة لاحقة"):
        db.commit()
    db.rollback()
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


def test_central_reading_checks_other_module_observations_and_reports_source(db):
    equipment = seed_equipment(db, "CROSS-1", "km")
    db.add(FuelRecord(
        equipment_id=equipment.id, fueling_date=datetime(2026, 8, 17).date(),
        sequence_number=1, meter_value=Decimal("700"), quantity=Decimal("20"),
    ))
    db.commit()

    with pytest.raises(ValueError, match="الوقود"):
        services.create_reading(db, equipment.id, odometer=710, reading_date=datetime(2026, 8, 17))
    with pytest.raises(ValueError, match="الوقود"):
        services.create_reading(db, equipment.id, odometer=690, reading_date=datetime(2026, 8, 18))

    created, rejected, errors, _warnings, ids = services.create_bulk_readings(
        db, [bulk_row(equipment, datetime(2026, 8, 17), 700, row_number=2)]
    )
    assert created == 0 and rejected == 1 and not ids
    assert any("الوقود" in error for error in errors)


def test_fuel_input_checks_central_reading_chronology(db):
    equipment = seed_equipment(db, "CROSS-2", "km")
    services.create_reading(db, equipment.id, odometer=700, reading_date=datetime(2026, 8, 17))
    with pytest.raises(ValueError, match="إدخال يدوي"):
        validate_fuel_record(db, equipment.id, datetime(2026, 8, 18).date(), Decimal("690"), Decimal("20"))

    add_fuel_record(db, {
        "equipment_id": equipment.id, "fueling_date": datetime(2026, 8, 18).date(),
        "sequence_number": None, "meter_value": Decimal("710"), "quantity": Decimal("20"),
    })
    assert equipment.current_odometer == Decimal("710.0")
    central = db.query(MeterReading).filter(MeterReading.source_reference.like("fuel:%")).one_or_none()
    assert central is not None
    assert central.source == "fuel"
    assert central.source_reference.startswith("fuel:")
    assert db.query(MeterReadingChange).filter(MeterReadingChange.reading_id == central.id, MeterReadingChange.action == "add").count() == 1


def test_latest_meter_list_includes_the_source_column_value(db):
    equipment = seed_equipment(db, "SRC-COL", "km")
    add_fuel_record(db, {
        "equipment_id": equipment.id, "fueling_date": datetime(2026, 8, 18).date(),
        "sequence_number": None, "meter_value": Decimal("710"), "quantity": Decimal("20"),
    })
    rows, *_ = services.list_latest_rows(db)
    row = next(item for item in rows if item["equipment_id"] == equipment.id)
    assert row["source"] == "الوقود"
    from pathlib import Path
    template = Path("app/modules/meter_readings/templates/meter_readings.html").read_text(encoding="utf-8")
    assert '<th>السجل</th>' not in template
    assert "مصدر آخر قراءة" in template
    assert 'class="meter-history-link"' in template


def test_latest_meter_list_filters_by_the_latest_reading_date(db):
    older = seed_equipment(db, "DATE-OLD", "km")
    matching = seed_equipment(db, "DATE-MATCH", "km")
    services.create_reading(db, older.id, odometer=100, reading_date=datetime(2026, 8, 17))
    services.create_reading(db, matching.id, odometer=200, reading_date=datetime(2026, 8, 18))

    rows, total, _pages, _last_update = services.list_latest_rows(
        db,
        date_from=datetime(2026, 8, 18),
        date_to=datetime(2026, 8, 18, 23, 59, 59, 999999),
    )

    assert total == 1
    assert [row["equipment_id"] for row in rows] == [matching.id]


def test_domain_models_do_not_have_local_meter_storage_columns():
    from app.modules.faults_repairs.models import Fault, Repair
    from app.modules.maintenance.models import MaintenanceRecord
    from app.modules.missions.models import Mission

    for model, columns in (
        (FuelRecord, {"meter_value"}),
        (Fault, {"meter_value"}),
        (Repair, {"meter_value"}),
        (MaintenanceRecord, {"meter_value"}),
        (Mission, {"departure_meter", "return_meter"}),
        (TireMovement, {"meter_value"}),
        (BatteryMovement, {"meter_value"}),
    ):
        assert not (columns & set(model.__table__.columns.keys()))


def test_clearing_a_source_value_unlinks_but_keeps_central_history(db):
    equipment = seed_equipment(db, "UNLINK-1", "km")
    record = add_fuel_record(db, {
        "equipment_id": equipment.id, "fueling_date": datetime(2026, 8, 18).date(),
        "sequence_number": None, "meter_value": Decimal("710"), "quantity": Decimal("20"),
    })
    central = db.query(MeterReading).filter_by(source_reference=f"fuel:{record.id}:meter").one()

    record.meter_value = None
    db.commit()
    db.refresh(record)
    db.refresh(central)

    assert record.meter_value is None
    assert central.odometer == Decimal("710.0")
    assert central.source_reference is None
    assert db.query(MeterReadingChange).filter_by(reading_id=central.id, action="unlink").count() == 1


def test_mission_input_advances_current_meter_from_return_reading(db):
    equipment = seed_equipment(db, "CROSS-3", "km")
    services.create_reading(db, equipment.id, odometer=700, reading_date=datetime(2026, 8, 17))
    add_mission(db, {
        "equipment_id": equipment.id, "start_date": datetime(2026, 8, 18).date(),
        "end_date": datetime(2026, 8, 19).date(), "departure_meter": Decimal("700"),
        "return_meter": Decimal("720"),
    })
    assert equipment.current_odometer == Decimal("720")
    rows = services.list_readings(db, equipment.id)
    assert [(row.source, row.odometer) for row in rows[-2:]] == [
        ("mission_departure", Decimal("700.0")),
        ("mission_return", Decimal("720.0")),
    ]
    assert all(row.source_reference.startswith("mission:") for row in rows[-2:])


@pytest.mark.parametrize(
    ("movement_model", "asset_model", "source", "registration"),
    [
        (TireMovement, Tire, "tire_movement", "CENTRAL-TIRE"),
        (BatteryMovement, Battery, "battery_movement", "CENTRAL-BATTERY"),
    ],
)
def test_component_movement_writes_one_central_meter_with_its_source(
    db, movement_model, asset_model, source, registration
):
    equipment = seed_equipment(db, registration, "km")
    asset = asset_model(serial_number=registration)
    db.add(asset)
    db.flush()
    when = datetime(2026, 8, 18, 10) if movement_model is TireMovement else datetime(2026, 8, 18)
    values = {
        "equipment_id": equipment.id,
        "movement_date": when.date(),
        "movement_type": "install",
        "meter_value": Decimal("730"),
    }
    if movement_model is TireMovement:
        values["movement_datetime"] = when
    movement = movement_model(**values)
    setattr(movement, "tire_id" if movement_model is TireMovement else "battery_id", asset.id)
    db.add(movement)
    db.commit()

    central = db.query(MeterReading).filter(MeterReading.source == source).one()
    assert central.odometer == Decimal("730.0")
    assert central.source_reference == f"{source}:{movement.id}:meter"
    assert equipment.current_odometer == Decimal("730.0")
    assert "meter_value" not in movement_model.__table__.columns
    db.expire(movement)
    assert movement.meter_value == Decimal("730.0")


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
