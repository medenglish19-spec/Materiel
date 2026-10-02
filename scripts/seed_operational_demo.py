"""Seed a self-contained operational-analysis demo dataset.

Run from the repository root:
    python scripts/seed_operational_demo.py
    python scripts/seed_operational_demo.py --remove

The dataset is clearly marked with DEMO-AN identifiers and can be removed
without touching unrelated records. It is not a production migration.
"""

import argparse
from datetime import date, datetime
from decimal import Decimal

from app.database.session import SessionLocal
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.meter_readings.models import MeterReading
from app.modules.missions.models import Mission
from app.modules.fuel.models import FuelRecord
from app.modules.faults_repairs.models import Fault, Repair
from app.modules.maintenance.models import (
    MaintenanceOperation,
    MaintenanceOperationGroup,
    MaintenanceRecord,
)


DEMO_PREFIX = "DEMO-AN-"
CATEGORY_NAME = "مثال تحليلي: مركبات"
TYPE_NAME = "مثال تحليلي: مركبة خفيفة"
BRAND_NAME = "مثال تحليلي: DemoBrand"
MODEL_NAME = "مثال تحليلي: Fleet-01"
GROUP_NAME = "مثال تحليلي: المحرك"
OPERATION_NAME = "مثال تحليلي: فحص المحرك الدوري"


def get_or_create(db, model, defaults=None, **filters):
    obj = db.query(model).filter_by(**filters).first()
    if obj is None:
        obj = model(**filters, **(defaults or {}))
        db.add(obj)
        db.flush()
    return obj


def remove_demo(db):
    equipment = db.query(Equipment).filter(Equipment.registration_number.like(f"{DEMO_PREFIX}%")).all()
    equipment_ids = [e.id for e in equipment]

    if equipment_ids:
        faults = db.query(Fault).filter(Fault.equipment_id.in_(equipment_ids)).all()
        fault_ids = [f.id for f in faults]
        if fault_ids:
            for repair in db.query(Repair).filter(Repair.fault_id.in_(fault_ids)).all():
                db.delete(repair)
        for fault in faults:
            db.delete(fault)
        for cls in (MeterReading, Mission, FuelRecord, MaintenanceRecord):
            for row in db.query(cls).filter(cls.equipment_id.in_(equipment_ids)).all():
                db.delete(row)
        db.flush()
        for e in equipment:
            db.delete(e)
        db.flush()

    operation = db.query(MaintenanceOperation).filter(MaintenanceOperation.name == OPERATION_NAME).first()
    if operation is not None:
        db.delete(operation)
        db.flush()
    group = db.query(MaintenanceOperationGroup).filter(MaintenanceOperationGroup.name == GROUP_NAME).first()
    if group is not None:
        db.delete(group)
        db.flush()

    model = db.query(EquipmentModel).filter(EquipmentModel.name == MODEL_NAME).first()
    if model is not None:
        db.delete(model)
        db.flush()
    equipment_type = db.query(EquipmentType).filter(EquipmentType.name == TYPE_NAME).first()
    if equipment_type is not None:
        db.delete(equipment_type)
        db.flush()
    brand = db.query(EquipmentBrand).filter(EquipmentBrand.name == BRAND_NAME).first()
    if brand is not None:
        db.delete(brand)
        db.flush()
    category = db.query(EquipmentCategory).filter(EquipmentCategory.name == CATEGORY_NAME).first()
    if category is not None:
        db.delete(category)

    db.commit()
    print("Operational demo data removed.")


def seed(db):
    # Re-running the seed replaces only its own dataset.
    remove_demo(db)

    category = get_or_create(db, EquipmentCategory, code="DEMO-AN", name=CATEGORY_NAME, sort_order=900)
    brand = get_or_create(db, EquipmentBrand, name=BRAND_NAME, is_active=True)
    equipment_type = get_or_create(
        db,
        EquipmentType,
        name=TYPE_NAME,
        measurement_unit="km",
        theoretical_quantity=4,
        category_id=category.id,
        is_frozen=False,
    )
    model = get_or_create(
        db,
        EquipmentModel,
        name=MODEL_NAME,
        equipment_type_id=equipment_type.id,
        brand_id=brand.id,
        is_frozen=False,
        has_tires=True,
        tire_positions_required=4,
        mobility_type="mobile",
        requires_driver=True,
    )

    group = get_or_create(db, MaintenanceOperationGroup, name=GROUP_NAME, sort_order=900)
    operation = get_or_create(
        db,
        MaintenanceOperation,
        name=OPERATION_NAME,
        interval_km=5000,
        warning_km=500,
        is_active=True,
        description="عملية تجريبية لاختبار الربط بين الصيانة والأعطال.",
        group_id=group.id,
    )

    specs = [
        ("DEMO-AN-001", "2026-01-01", "2026-06-30", 10000, 15000, 1200, 12000, "available"),
        ("DEMO-AN-002", "2026-01-01", "2026-06-30", 20000, 23000, 330, 21500, "available"),
        ("DEMO-AN-003", "2026-01-01", "2026-06-30", 30000, 34500, 540, 33500, "in_maintenance"),
        ("DEMO-AN-004", "2026-01-01", "2026-06-30", 40000, 42000, 210, 41000, "available"),
    ]

    created = {}
    for reg, start_s, end_s, start_meter, end_meter, fuel, mission_end, status in specs:
        e = Equipment(
            asset_code=f"DEMO-INTERNAL-{reg[-3:]}",
            registration_number=reg,
            vin=f"DEMO-VIN-{reg[-3:]}",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model.id,
            acquisition_date=date(2023, 1, 1),
            first_service_date=date(2023, 2, 1),
            technical_condition="ready" if reg != "DEMO-AN-003" else "ready_restricted",
            operational_status=status,
            current_odometer=end_meter,
            current_hours=0,
            notes="بيانات تجريبية للتحليل التشغيلي فقط.",
        )
        db.add(e)
        db.flush()
        created[reg] = e

        start = datetime.fromisoformat(f"{start_s}T08:00:00")
        end = datetime.fromisoformat(f"{end_s}T08:00:00")
        db.add(MeterReading(
            equipment_id=e.id, reading_date=start, odometer=Decimal(start_meter),
            source="demo", equipment_status="available",
        ))
        db.add(MeterReading(
            equipment_id=e.id, reading_date=end, odometer=Decimal(end_meter),
            source="demo", equipment_status=status,
        ))

        db.add(Mission(
            equipment_id=e.id, driver_name="سائق تجريبي",
            mission_document=f"{reg}-M1", purpose="اختبار التحليل",
            destination="ميدان تجريبي", start_date=date(2026, 5, 10),
            end_date=date(2026, 5, 10), departure_meter=Decimal(end_meter - 500),
            return_meter=Decimal(end_meter), notes="مهمة تجريبية.",
        ))

        db.add(FuelRecord(
            equipment_id=e.id, fueling_date=date(2026, 6, 15),
            sequence_number=1, meter_value=Decimal(end_meter - 100),
            quantity=Decimal(str(fuel)), fuel_type="diesel",
            document_number=f"{reg}-F1", station="محطة تجريبية",
        ))

        db.add(MaintenanceRecord(
            equipment_id=e.id, operation_id=operation.id,
            maintenance_date=date(2026, 4, 1), reported_date=date(2026, 4, 1),
            meter_value=Decimal(start_meter + 2500),
            work_order=f"{reg}-PM1", workshop="الورشة الداخلية",
            status="completed", is_scheduled=True,
            description="صيانة دورية تجريبية.",
        ))

    def add_fault(reg, fault_date, fault_type, severity="medium", impact="none", status="closed"):
        e = created[reg]
        f = Fault(
            equipment_id=e.id,
            reported_date=date.fromisoformat(fault_date),
            report_number=f"{reg}-FLT-{len(faults_created[reg]) + 1}",
            meter_value=Decimal(str(fault_meter[reg])),
            fault_type=fault_type,
            description=f"عطل تجريبي: {fault_type}",
            severity=severity,
            status=status,
            exploitation_impact=impact,
        )
        db.add(f)
        db.flush()
        faults_created[reg].append(f)
        return f

    faults_created = {reg: [] for reg, *_ in specs}
    fault_meter = {
        "DEMO-AN-001": 12500,
        "DEMO-AN-002": 21500,
        "DEMO-AN-003": 33000,
        "DEMO-AN-004": 41500,
    }

    # Unit 001: higher fault burden than its peers, with active repair history.
    f = add_fault("DEMO-AN-001", "2026-02-10", "ارتفاع حرارة", "high", "limited", "repaired")
    db.add(Repair(fault_id=f.id, repair_date=date(2026, 2, 11), meter_value=12510,
                   diagnosis="فحص نظام التبريد", action_taken="تنظيف وفحص", workshop_type="internal",
                   workshop="الورشة الداخلية", labor_hours=2, status="completed"))
    f = add_fault("DEMO-AN-001", "2026-03-12", "ارتفاع حرارة", "high", "prohibited", "open")
    db.add(Repair(fault_id=f.id, repair_date=date(2026, 3, 13), meter_value=12800,
                   diagnosis="تشخيص أولي", action_taken="فحص مضخة التبريد", workshop_type="internal",
                   workshop="الورشة الداخلية", labor_hours=3, status="in_progress"))
    add_fault("DEMO-AN-001", "2026-04-20", "تسرب زيت", "medium", "limited", "closed")
    add_fault("DEMO-AN-001", "2026-06-01", "ارتفاع حرارة", "high", "limited", "repaired")

    # Units 002 and 003 share the same fault type to create a peer pattern.
    f = add_fault("DEMO-AN-002", "2026-04-15", "ارتفاع حرارة", "medium", "none", "repaired")
    db.add(Repair(fault_id=f.id, repair_date=date(2026, 4, 16), meter_value=22000,
                   diagnosis="فحص", action_taken="تغيير خرطوم", workshop_type="internal",
                   workshop="الورشة الداخلية", labor_hours=1.5, status="completed"))
    add_fault("DEMO-AN-003", "2026-05-03", "ارتفاع حرارة", "high", "prohibited", "repaired")
    f = add_fault("DEMO-AN-003", "2026-06-20", "فرامل", "critical", "prohibited", "open")
    db.add(Repair(fault_id=f.id, repair_date=date(2026, 6, 21), meter_value=34000,
                   diagnosis="تشخيص نظام الفرامل", action_taken="استبدال قطعة", workshop_type="external",
                   workshop="ورشة خارجية تجريبية", external_dispatch_document="DEMO-DISPATCH-003", labor_hours=5, status="in_progress"))

    db.commit()
    print("Operational demo data installed:")
    print("  - 4 comparable units: DEMO-AN-001 .. DEMO-AN-004")
    print("  - meter history + missions + fuel")
    print("  - faults + repairs + scheduled maintenance")
    print("  - peer comparison and repeated-fault patterns")
    print("  - one open/prohibited fault with repair activity")


def main():
    parser = argparse.ArgumentParser(description="Materiel operational-analysis demo data")
    parser.add_argument("--remove", action="store_true", help="remove only the demo dataset")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.remove:
            remove_demo(db)
        else:
            seed(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
