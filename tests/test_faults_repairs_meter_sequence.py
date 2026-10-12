"""Regression tests for the unified meter-sequence validation in faults/repairs.

The faults and repairs modules store their own ``meter_value``; it must obey the
same chronological rule as the central MeterReading, and it must be checked
against every source that carries a meter observation (MeterReading,
MaintenanceRecord, Fault, Repair).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.faults_repairs import services as fault_services
from app.modules.faults_repairs.models import Fault, Repair
from app.modules.faults_repairs.schemas import FaultCreate, FaultUpdate, RepairCreate
from app.modules.maintenance.models import (
    MaintenanceOperation,
    MaintenanceRecord,
    maintenance_operation_models,
)
from app.modules.meter_readings import services as meter_services
from app.modules.meter_readings.models import MeterReading
from app.modules.users.models import User  # noqa: F401  (registers the users table for FKs)

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)

TODAY = date.today()


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def seed_equipment(db, registration, unit="km"):
    equipment_type = EquipmentType(name=f"نوع-{registration}", measurement_unit=unit)
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name=f"طراز-{registration}", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code=f"A-{registration}",
        registration_number=registration,
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
        operational_status="available",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def add_reading(db, equipment, day, value):
    when = datetime(day.year, day.month, day.day)
    if equipment.equipment_type.measurement_unit == "km":
        return meter_services.create_reading(db, equipment.id, odometer=value, reading_date=when)
    return meter_services.create_reading(db, equipment.id, hours=value, reading_date=when)


def add_maintenance_record(db, equipment, day, value):
    operation = MaintenanceOperation(name=f"عملية-{equipment.id}-{day.isoformat()}", is_active=True)
    db.add(operation)
    db.flush()
    db.execute(
        maintenance_operation_models.insert().values(
            operation_id=operation.id,
            equipment_model_id=equipment.equipment_model_id,
            condition_source="model",
            interval_km=5000,
            is_active=True,
        )
    )
    record = MaintenanceRecord(
        equipment_id=equipment.id,
        operation_id=operation.id,
        maintenance_date=day,
        meter_value=Decimal(str(value)),
        status="completed",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_fault(db, equipment, day, value):
    return fault_services.create_fault(
        db,
        FaultCreate(
            equipment_id=equipment.id,
            reported_date=day,
            meter_value=Decimal(str(value)),
            fault_type="engine",
            description="عطل اختبار",
            severity="medium",
        ),
    )


def create_repair(db, fault, day, value):
    return fault_services.create_repair(
        db,
        RepairCreate(
            fault_id=fault.id,
            repair_date=day,
            meter_value=Decimal(str(value)),
            action_taken="إصلاح اختبار",
            workshop_type="internal",
            status="in_progress",
        ),
    )


# ---------------------------------------------------------------------------
# Creation: the central MeterReading must not be bypassed backwards.
# ---------------------------------------------------------------------------


def test_fault_cannot_go_backwards_past_central_reading(db):
    equipment = seed_equipment(db, "FKM-1", "km")
    add_reading(db, equipment, TODAY - timedelta(days=9), 20)

    before_faults = db.query(Fault).count()
    before_readings = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count()

    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        create_fault(db, equipment, TODAY, 10)

    # No fault row and no central artifact left behind.
    assert db.query(Fault).count() == before_faults
    assert db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).count() == before_readings


def test_repair_cannot_go_backwards_past_central_reading(db):
    equipment = seed_equipment(db, "FKM-2", "km")
    add_reading(db, equipment, TODAY - timedelta(days=9), 20)
    fault = create_fault(db, equipment, TODAY - timedelta(days=5), 20)
    fault_services.change_fault_status(db, fault, "diagnosing")

    before_repairs = db.query(Repair).count()
    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        create_repair(db, fault, TODAY, 5)

    assert db.query(Repair).count() == before_repairs


def test_increasing_meter_is_allowed_and_saved_once(db):
    equipment = seed_equipment(db, "FKM-3", "km")
    add_reading(db, equipment, TODAY - timedelta(days=9), 20)

    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 25)

    assert fault.id is not None
    assert db.query(Fault).filter(Fault.equipment_id == equipment.id).count() == 1


# ---------------------------------------------------------------------------
# Unit separation: km and hours are never compared with each other.
# ---------------------------------------------------------------------------


def test_hours_equipment_reads_the_hours_column_only(db):
    equipment = seed_equipment(db, "HRS-1", "hours")
    reading = add_reading(db, equipment, TODAY - timedelta(days=9), 100)

    assert reading.hours == Decimal("100.0")
    assert reading.odometer is None

    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        create_fault(db, equipment, TODAY, 50)

    fault = create_fault(db, equipment, TODAY, 120)
    assert fault.meter_value == Decimal("120.0")

    stored = db.query(MeterReading).filter(MeterReading.equipment_id == equipment.id).all()
    assert len(stored) == 1
    assert all(row.odometer is None for row in stored)


# ---------------------------------------------------------------------------
# Chronology: the latest *date* wins, not the largest meter value.
# ---------------------------------------------------------------------------


def test_latest_before_uses_chronology_not_maximum_value(db):
    equipment = seed_equipment(db, "CHR-1", "km")

    # Contradictory historical history: an older, higher reading followed by a
    # corrected lower one. Inserted through the table to bypass the event
    # listeners that would otherwise reject this pre-existing inconsistency.
    table = MeterReading.__table__
    db.execute(
        insert(table).values(
            equipment_id=equipment.id,
            reading_date=datetime.combine(TODAY - timedelta(days=20), datetime.min.time()),
            odometer=100,
            source="manual",
            equipment_status="available",
        )
    )
    db.execute(
        insert(table).values(
            equipment_id=equipment.id,
            reading_date=datetime.combine(TODAY - timedelta(days=10), datetime.min.time()),
            odometer=50,
            source="manual",
            equipment_status="available",
        )
    )
    db.commit()

    latest = fault_services._latest_meter_before(db, equipment.id, TODAY - timedelta(days=5), "km")
    assert latest == Decimal("50.0")

    # 40 is below the latest earlier reading (50) and is rejected.
    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        create_fault(db, equipment, TODAY - timedelta(days=4), 40)

    # 60 is above the latest earlier reading and must not be blocked by the
    # older, higher 100 reading.
    fault = create_fault(db, equipment, TODAY - timedelta(days=4), 60)
    assert fault.id is not None


def test_all_sources_participate_in_the_comparison(db):
    equipment = seed_equipment(db, "SRC-1", "km")
    add_maintenance_record(db, equipment, TODAY - timedelta(days=30), 30)
    add_reading(db, equipment, TODAY - timedelta(days=20), 20)
    fault = create_fault(db, equipment, TODAY - timedelta(days=15), 25)
    fault_services.change_fault_status(db, fault, "diagnosing")
    create_repair(db, fault, TODAY - timedelta(days=12), 28)

    # The most recent earlier observation is the repair (28), so 22 is rejected.
    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        create_fault(db, equipment, TODAY, 22)

    # 29 is above every earlier observation and is accepted.
    ok = create_fault(db, equipment, TODAY, 29)
    assert ok.id is not None


def test_same_day_value_must_match(db):
    equipment = seed_equipment(db, "SAME-1", "km")
    day = TODAY - timedelta(days=5)
    add_reading(db, equipment, day, 20)

    # The same value on the same day is consistent.
    fault = create_fault(db, equipment, day, 20)
    assert fault.id is not None

    # A different value on the same day is a conflict.
    with pytest.raises(ValueError, match="نفس التاريخ"):
        create_fault(db, equipment, day, 25)


# ---------------------------------------------------------------------------
# Editing: the row is excluded from its own comparison, later readings are
# still enforced, and a rejected edit leaves no partial change behind.
# ---------------------------------------------------------------------------


def test_update_fault_excludes_itself_and_keeps_no_partial_change(db):
    equipment = seed_equipment(db, "UPD-1", "km")
    add_reading(db, equipment, TODAY - timedelta(days=9), 20)
    fault = create_fault(db, equipment, TODAY - timedelta(days=5), 30)

    # Lowering to 25 is valid: the row must not be compared with its own old 30.
    updated = fault_services.update_fault(db, fault, FaultUpdate(meter_value=Decimal("25")))
    assert updated.meter_value == Decimal("25.0")

    # 15 is below the central reading (20), so the edit is rejected...
    with pytest.raises(ValueError, match="أقل من قراءة سابقة"):
        fault_services.update_fault(db, fault, FaultUpdate(meter_value=Decimal("15")))

    # ...and no partial change was left in the in-memory object or the row.
    assert fault.meter_value == Decimal("25.0")
    db.expire_all()
    stored = db.query(Fault).filter(Fault.id == fault.id).one()
    assert stored.meter_value == Decimal("25.0")


def test_update_fault_rejects_conflict_with_a_later_reading(db):
    equipment = seed_equipment(db, "UPD-2", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=10), 30)
    add_reading(db, equipment, TODAY - timedelta(days=5), 40)

    with pytest.raises(ValueError, match="أكبر من قراءة لاحقة"):
        fault_services.update_fault(db, fault, FaultUpdate(meter_value=Decimal("45")))

    assert fault.meter_value == Decimal("30.0")
    db.expire_all()
    stored = db.query(Fault).filter(Fault.id == fault.id).one()
    assert stored.meter_value == Decimal("30.0")

# ---------------------------------------------------------------------------
# Active repair lifecycle: one mutable active row, immutable repair history.
# ---------------------------------------------------------------------------


def test_saving_active_repair_updates_the_same_row(db):
    equipment = seed_equipment(db, "ACTIVE-1", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 20)
    fault_services.change_fault_status(db, fault, "diagnosing")

    active = create_repair(db, fault, TODAY, 25)
    active_id = active.id
    assert active.status == "in_progress"

    saved = fault_services.create_repair(
        db,
        RepairCreate(
            fault_id=fault.id,
            repair_date=TODAY,
            meter_value=Decimal("25"),
            action_taken="نتيجة الإصلاح",
            workshop_type="internal",
            status="completed",
        ),
    )

    assert saved.id == active_id
    assert saved.status == "completed"
    assert saved.action_taken == "نتيجة الإصلاح"
    assert db.query(Repair).filter(Repair.fault_id == fault.id).count() == 1
    db.refresh(fault)
    assert fault.status == "repaired"


def test_completed_repair_stays_in_history_when_a_new_repair_starts(db):
    equipment = seed_equipment(db, "ACTIVE-2", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 20)
    fault_services.change_fault_status(db, fault, "diagnosing")
    previous = fault_services.create_repair(
        db,
        RepairCreate(
            fault_id=fault.id,
            repair_date=TODAY,
            meter_value=Decimal("25"),
            action_taken="التصليح الأول",
            workshop_type="internal",
            status="completed",
        ),
    )
    previous_id = previous.id

    fault_services.change_fault_status(db, fault, "diagnosing")
    current = create_repair(db, fault, TODAY, 25)

    assert current.id != previous_id
    assert current.status == "in_progress"
    assert db.query(Repair).filter(Repair.fault_id == fault.id).count() == 2
    db.refresh(previous)
    assert previous.status == "completed"


def test_completed_repair_cannot_be_reopened(db):
    equipment = seed_equipment(db, "ACTIVE-3", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 20)
    fault_services.change_fault_status(db, fault, "diagnosing")
    repair = fault_services.create_repair(
        db,
        RepairCreate(
            fault_id=fault.id,
            repair_date=TODAY,
            meter_value=Decimal("25"),
            action_taken="تصليح مكتمل",
            workshop_type="internal",
            status="completed",
        ),
    )

    with pytest.raises(ValueError, match="تاريخي"):
        fault_services.change_repair_status(db, repair, "in_progress")
    assert repair.status == "completed"

def test_fault_cannot_be_marked_repaired_while_repair_is_active(db):
    equipment = seed_equipment(db, "ACTIVE-4", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 20)
    fault_services.change_fault_status(db, fault, "diagnosing")
    create_repair(db, fault, TODAY, 25)

    with pytest.raises(ValueError, match="نتيجة سجل التصليح النشط"):
        fault_services.change_fault_status(db, fault, "repaired")

    db.refresh(fault)
    assert fault.status == "repairing"

def test_database_rejects_two_active_repairs_for_the_same_fault(db):
    equipment = seed_equipment(db, "ACTIVE-DB-1", "km")
    fault = create_fault(db, equipment, TODAY - timedelta(days=1), 20)

    values = {
        "fault_id": fault.id,
        "repair_date": TODAY,
        "action_taken": "إجراء اختبار",
        "workshop_type": "internal",
        "status": "in_progress",
    }
    db.execute(Repair.__table__.insert().values(**values))
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(Repair.__table__.insert().values(**values))
        db.commit()

    db.rollback()
    active_count = db.query(Repair).filter(
        Repair.fault_id == fault.id,
        Repair.status == "in_progress",
    ).count()
    assert active_count == 1

