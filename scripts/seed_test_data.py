"""Controlled, removable integration dataset for manual/local testing.

This module is never imported by application startup and never runs as a migration.
Use:
    python scripts/seed_test_data.py seed
    python scripts/seed_test_data.py clean
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database import model_registry  # noqa: F401
from app.database.session import _make_engine
from app.modules.batteries import services as battery_services
from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentModelSpecDefinition,
    EquipmentModelSpecValue,
    EquipmentType,
)
from app.modules.faults_repairs.models import (
    Fault,
    Repair,
    RepairPart,
    SparePart,
    Technician,
    TechnicianIntervention,
)
from app.modules.maintenance.models import (
    MaintenanceOperation,
    MaintenanceOperationGroup,
    MaintenancePlan,
    MaintenancePlanOperation,
    MaintenanceRecord,
)
from app.modules.meter_readings.audit import MeterReadingChange
from app.modules.meter_readings.models import MeterReading
from app.modules.missions import services as mission_services
from app.modules.missions.models import Mission
from app.modules.spare_parts_movements.models import (
    SparePartMovementDocument,
    SparePartMovementItem,
)
from app.modules.spare_parts_movements.schemas import (
    MovementDocumentCreate,
    MovementItemCreate,
)
from app.modules.spare_parts_movements import services as movement_services
from app.modules.spare_parts_requests.models import SparePartRequest
from app.modules.spare_parts_requests.schemas import (
    SparePartRequestCreate,
    SparePartRequestItemCreate,
)
from app.modules.spare_parts_requests import services as request_services
from app.modules.tires import services as tire_services
from app.modules.tires.models import Tire, TireDisposal, TireModelSize, TirePosition


MARKER = "TEST-SEED-20261007"
WAREHOUSE = f"المخزن المركزي — {MARKER}"
SUPPLIER = f"مؤسسة التموين المركزي — {MARKER}"
DISTRIBUTION_RECIPIENT = f"ورشة الصيانة — {MARKER}"

CATEGORY_SPECS = [
    ("مركبات النقل", "CAT-TRUCK", "شاحنات", "Iveco", "Daily 70C"),
    ("مولدات الطاقة", "CAT-GEN", "مولدات", "Caterpillar", "DE220E0"),
    ("معدات الأشغال", "CAT-WORK", "حفارات", "Komatsu", "PC210"),
]


def _db_url(value: str | None) -> str:
    return value or settings.DATABASE_URL


def _session(database_url: str | None = None):
    engine = _make_engine(_db_url(database_url))
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _assert_clean(db: Session) -> None:
    checks = [
        ("categories", db.query(EquipmentCategory.id).filter(EquipmentCategory.code.like(f"{MARKER}%")).first()),
        ("types", db.query(EquipmentType.id).filter(EquipmentType.name.like(f"{MARKER}%")).first()),
        ("models", db.query(EquipmentModel.id).filter(EquipmentModel.name.like(f"{MARKER}%")).first()),
        ("equipment", db.query(Equipment.id).filter(Equipment.asset_code.like(f"{MARKER}%")).first()),
        ("technicians", db.query(Technician.id).filter(Technician.employee_number.like(f"{MARKER}%")).first()),
        ("tires", db.query(Tire.id).filter(Tire.serial_number.like(f"{MARKER}%")).first()),
        ("batteries", db.query(Battery.id).filter(Battery.serial_number.like(f"{MARKER}%")).first()),
        ("faults", db.query(Fault.id).filter(Fault.report_number.like(f"{MARKER}%")).first()),
        ("requests", db.query(SparePartRequest.id).filter(SparePartRequest.request_number.like(f"{MARKER}%")).first()),
        ("movements", db.query(SparePartMovementDocument.id).filter(SparePartMovementDocument.document_number.like(f"{MARKER}%")).first()),
    ]
    existing = [name for name, row in checks if row is not None]
    if existing:
        raise RuntimeError(
            "بيانات الاختبار موجودة مسبقًا: "
            + ", ".join(existing)
            + ". نفّذ clean أولًا؛ seed لا يحذف شيئًا تلقائيًا."
        )


def _create_master_data(db: Session):
    categories = {}
    brands = {}
    types = {}
    models = {}
    positions = {}
    spec_definitions = {}

    for idx, (category_name, category_code, type_name, brand_name, model_name) in enumerate(CATEGORY_SPECS, start=1):
        category = EquipmentCategory(
            name=f"{MARKER} — {category_name}",
            code=f"{MARKER}-{category_code}",
            sort_order=idx,
            is_system=False,
        )
        brand = EquipmentBrand(name=f"{MARKER} — {brand_name}", is_active=True)
        db.add_all([category, brand])
        db.flush()

        unit = "hours" if idx == 2 else "km"
        equipment_type = EquipmentType(
            name=f"{MARKER} — {type_name}",
            measurement_unit=unit,
            category_id=category.id,
            theoretical_quantity=3,
        )
        db.add(equipment_type)
        db.flush()

        model = EquipmentModel(
            name=f"{MARKER} — {model_name}",
            equipment_type_id=equipment_type.id,
            brand_id=brand.id,
            has_tires=True,
            tire_positions_required=2,
            tire_size=("10R20" if idx == 1 else "23.5R25"),
            axle_count=1,
            has_batteries=True,
            battery_count_required=1,
            battery_capacity_ah=(180 if idx == 2 else 150),
            battery_voltage_v=24,
            mobility_type="mobile",
            requires_driver=True,
        )
        db.add(model)
        db.flush()

        categories[idx] = category
        brands[idx] = brand
        types[idx] = equipment_type
        models[idx] = model

        for pos_idx, side in enumerate(("يمين", "يسار"), start=1):
            position = TirePosition(
                code=f"{MARKER}-TP-{idx}-{pos_idx}",
                name=f"{MARKER} — محور {side}",
                description="موضع إطار لبيانات الاختبار",
                sort_order=pos_idx,
                equipment_model_id=model.id,
                axle_number=1,
                side=("right" if pos_idx == 1 else "left"),
                position_type="single",
            )
            db.add(position)
            positions[(idx, pos_idx)] = position

        db.add(TireModelSize(equipment_model_id=model.id, size=model.tire_size))

        definitions = [
            ("قدرة المحرك", "engine_power", "kW", "number"),
            ("سعة الوقود", "fuel_capacity", "L", "number"),
            ("ملاحظات تشغيلية", "operational_note", None, "text"),
        ]
        for spec_idx, (name, code, unit_spec, data_type) in enumerate(definitions, start=1):
            definition = EquipmentModelSpecDefinition(
                name=f"{MARKER} — {name} — {idx}",
                code=f"{MARKER}-{code}-{idx}",
                data_type=data_type,
                unit=unit_spec,
                sort_order=spec_idx,
                group_name="بيانات اختبارية",
                group_sort_order=1,
                equipment_type_id=equipment_type.id,
                category_id=category.id,
            )
            db.add(definition)
            db.flush()
            spec_definitions[(idx, spec_idx)] = definition
            value = (
                str(220 + idx * 20)
                if code == "engine_power"
                else str(400 + idx * 100)
                if code == "fuel_capacity"
                else f"بيانات اختبارية مترابطة للطراز {idx}"
            )
            db.add(EquipmentModelSpecValue(
                equipment_model_id=model.id,
                spec_definition_id=definition.id,
                value=value,
            ))

    db.flush()
    return categories, brands, types, models, positions, spec_definitions


def _create_equipment(db: Session, types, models):
    equipment = []
    registrations = [
        "001245-16-01", "002468-16-01", "003781-16-01",
        "001126-19-01", "002347-19-01", "003568-19-01",
        "001459-25-01", "002670-25-01", "003891-25-01",
    ]
    for idx in range(9):
        model_idx = idx // 3 + 1
        unit = types[model_idx].measurement_unit
        base = Decimal("10000") + Decimal(idx * 750)
        eq = Equipment(
            asset_code=f"{MARKER}-EQ-{idx + 1:02d}",
            registration_number=registrations[idx],
            vin=f"{MARKER}-VIN-{idx + 1:02d}",
            equipment_type_id=types[model_idx].id,
            equipment_model_id=models[model_idx].id,
            acquisition_document=f"{MARKER}-ACQ-{idx + 1:02d}",
            acquisition_date=date.today() - timedelta(days=400 + idx * 10),
            first_service_date=date.today() - timedelta(days=360 + idx * 10),
            technical_condition="ready",
            operational_status="available",
            current_odometer=(Decimal("5000") + Decimal(idx * 500) if unit == "km" else Decimal("0")),
            current_hours=(Decimal("300") + Decimal(idx * 25) if unit == "hours" else Decimal("0")),
            notes=f"معدات اختبارية مرتبطة بالكامل بالبيانات {MARKER}",
        )
        db.add(eq)
        equipment.append(eq)
    db.flush()
    return equipment


def _create_meters(db: Session, equipment):
    today = date.today()
    for idx, eq in enumerate(equipment):
        model_idx = idx // 3 + 1
        unit = "hours" if model_idx == 2 else "km"
        first_value = Decimal("1000") + Decimal(idx * 250)
        second_value = first_value + Decimal("120")
        if unit == "km":
            values = ({"odometer": first_value, "hours": None}, {"odometer": second_value, "hours": None})
        else:
            values = ({"odometer": None, "hours": first_value / 10}, {"odometer": None, "hours": second_value / 10})
        for offset, payload in ((30, values[0]), (10, values[1])):
            db.add(MeterReading(
                equipment_id=eq.id,
                reading_date=datetime.combine(today - timedelta(days=offset), time(8, 0)),
                odometer=payload["odometer"],
                hours=payload["hours"],
                source=f"{MARKER}-meter",
                equipment_status="available",
                notes=f"قراءة عداد اختبارية — {MARKER}",
            ))
    db.flush()


def _create_tires_and_batteries(db: Session, equipment, models, positions):
    today = date.today()
    for idx, eq in enumerate(equipment):
        model_idx = idx // 3 + 1
        model_unit = "hours" if model_idx == 2 else "km"
        base_meter = (
            Decimal("100") + Decimal(idx * 25)
            if model_unit == "hours"
            else Decimal("1000") + Decimal(idx * 250)
        )
        later_meter = base_meter + (Decimal("12") if model_unit == "hours" else Decimal("120"))
        movement_meter = base_meter if model_unit == "km" else None
        later_movement_meter = later_meter if model_unit == "km" else None
        for pos_idx in (1, 2):
            tire = Tire(
                serial_number=f"{MARKER}-TIRE-{idx + 1:02d}-{pos_idx}",
                brand=f"{MARKER} — Michelin",
                model=f"{MARKER} — X Multi",
                size=models[model_idx].tire_size,
                manufacture_date=today - timedelta(days=180),
                receipt_date=today - timedelta(days=120),
                expiry_date=today + timedelta(days=900),
                acquisition_document=f"{MARKER}-TIRE-REC-{idx + 1:02d}-{pos_idx}",
                notes=f"إطار اختبار {MARKER}",
            )
            db.add(tire)
            db.flush()
            tire_services.add_movement(
                db,
                tire.id,
                {
                    "movement_date": today - timedelta(days=20),
                    "movement_datetime": datetime.combine(today - timedelta(days=20), time(9, pos_idx)),
                    "movement_type": "install",
                    "equipment_id": eq.id,
                    "position_id": positions[(model_idx, pos_idx)].id,
                    "meter_value": movement_meter,
                    "document_number": f"{MARKER}-TIRE-IN-{idx + 1:02d}-{pos_idx}",
                    "reason": None,
                    "notes": f"تركيب أولي — {MARKER}",
                },
            )

        battery = Battery(
            serial_number=f"{MARKER}-BAT-{idx + 1:02d}",
            brand=f"{MARKER} — Varta",
            model=f"{MARKER} — Heavy Duty",
            manufacture_date=today - timedelta(days=150),
            receipt_date=today - timedelta(days=100),
            expiry_date=today + timedelta(days=500),
            acquisition_document=f"{MARKER}-BAT-REC-{idx + 1:02d}",
            notes=f"بطارية اختبار {MARKER}",
        )
        db.add(battery)
        db.flush()
        battery_services.add_movement(
            db,
            battery.id,
            {
                "movement_date": today - timedelta(days=20),
                "movement_type": "install",
                "equipment_id": eq.id,
                "meter_value": movement_meter,
                "document_number": f"{MARKER}-BAT-IN-{idx + 1:02d}",
                "reason": None,
                "notes": f"تركيب أولي — {MARKER}",
            },
        )

        if idx in (0, 3, 6):
            replacement_tire = Tire(
                serial_number=f"{MARKER}-TIRE-R-{idx + 1:02d}",
                brand=f"{MARKER} — Michelin",
                model=f"{MARKER} — X Multi Replacement",
                size=models[model_idx].tire_size,
                manufacture_date=today - timedelta(days=90),
                receipt_date=today - timedelta(days=60),
                expiry_date=today + timedelta(days=960),
                acquisition_document=f"{MARKER}-TIRE-REP-REC-{idx + 1:02d}",
                notes=f"إطار بديل اختبار {MARKER}",
            )
            db.add(replacement_tire)
            db.flush()
            original_tire = (
                db.query(Tire)
                .filter(Tire.serial_number == f"{MARKER}-TIRE-{idx + 1:02d}-1")
                .one()
            )
            tire_services.add_movement(
                db,
                original_tire.id,
                {
                    "movement_date": today - timedelta(days=8),
                    "movement_datetime": datetime.combine(today - timedelta(days=8), time(10, 1)),
                    "movement_type": "remove",
                    "equipment_id": None,
                    "position_id": None,
                    "meter_value": later_movement_meter,
                    "document_number": f"{MARKER}-TIRE-OUT-{idx + 1:02d}",
                    "reason": "استبدال وقائي",
                    "removal_disposition": "stock",
                    "notes": f"فك لأغراض الاختبار — {MARKER}",
                },
            )
            tire_services.add_movement(
                db,
                replacement_tire.id,
                {
                    "movement_date": today - timedelta(days=7),
                    "movement_datetime": datetime.combine(today - timedelta(days=7), time(10, 2)),
                    "movement_type": "install",
                    "equipment_id": eq.id,
                    "position_id": positions[(model_idx, 1)].id,
                    "meter_value": (later_movement_meter + Decimal("20")) if later_movement_meter is not None else None,
                    "document_number": f"{MARKER}-TIRE-REP-IN-{idx + 1:02d}",
                    "reason": None,
                    "notes": f"تركيب بديل — {MARKER}",
                },
            )

            replacement_battery = Battery(
                serial_number=f"{MARKER}-BAT-R-{idx + 1:02d}",
                brand=f"{MARKER} — Varta",
                model=f"{MARKER} — Replacement",
                manufacture_date=today - timedelta(days=80),
                receipt_date=today - timedelta(days=50),
                expiry_date=today + timedelta(days=600),
                acquisition_document=f"{MARKER}-BAT-REP-REC-{idx + 1:02d}",
                notes=f"بطارية بديلة اختبار {MARKER}",
            )
            db.add(replacement_battery)
            db.flush()
            original_battery = (
                db.query(Battery)
                .filter(Battery.serial_number == f"{MARKER}-BAT-{idx + 1:02d}")
                .one()
            )
            battery_services.add_movement(
                db,
                original_battery.id,
                {
                    "movement_date": today - timedelta(days=8),
                    "movement_type": "remove",
                    "equipment_id": None,
                    "meter_value": later_movement_meter,
                    "document_number": f"{MARKER}-BAT-OUT-{idx + 1:02d}",
                    "reason": "استبدال وقائي",
                    "notes": f"فك لأغراض الاختبار — {MARKER}",
                },
            )
            battery_services.add_movement(
                db,
                replacement_battery.id,
                {
                    "movement_date": today - timedelta(days=7),
                    "movement_type": "install",
                    "equipment_id": eq.id,
                    "meter_value": (later_movement_meter + Decimal("20")) if later_movement_meter is not None else None,
                    "document_number": f"{MARKER}-BAT-REP-IN-{idx + 1:02d}",
                    "reason": None,
                    "notes": f"تركيب بديل — {MARKER}",
                },
            )


def _create_maintenance(db: Session, equipment, models):
    today = date.today()
    groups = []
    operations = []
    plans = []
    for idx in range(1, 4):
        group = MaintenanceOperationGroup(name=f"{MARKER} — مجموعة الصيانة {idx}", sort_order=idx)
        db.add(group)
        db.flush()
        unit = "hours" if idx == 2 else "km"
        operation = MaintenanceOperation(
            name=f"{MARKER} — عملية الصيانة {idx}",
            interval_km=(5000 if unit == "km" else None),
            interval_hours=(250 if unit == "hours" else None),
            interval_days=180,
            warning_km=(500 if unit == "km" else None),
            warning_days=20,
            description=f"عملية صيانة دورية اختبارية {MARKER}",
            group_id=group.id,
        )
        db.add(operation)
        db.flush()
        plan = MaintenancePlan(
            equipment_model_id=models[idx].id,
            name=f"{MARKER} — خطة طراز {idx}",
            interval_km=(5000 if unit == "km" else None),
            interval_hours=(250 if unit == "hours" else None),
            interval_days=180,
            description=f"خطة مرتبطة بالطراز {idx} — {MARKER}",
        )
        db.add(plan)
        db.flush()
        db.add(MaintenancePlanOperation(plan_id=plan.id, operation_id=operation.id, sort_order=1))
        groups.append(group)
        operations.append(operation)
        plans.append(plan)

    db.flush()

    for idx, eq in enumerate(equipment):
        model_idx = idx // 3 + 1
        unit = "hours" if model_idx == 2 else "km"
        meter = (Decimal("1150") + Decimal(idx * 250)) if unit == "km" else (Decimal("190") + Decimal((idx - 3) * 25))
        db.add(MaintenanceRecord(
            equipment_id=eq.id,
            operation_id=operations[model_idx - 1].id,
            plan_id=plans[model_idx - 1].id,
            maintenance_date=today - timedelta(days=5),
            reported_date=today - timedelta(days=5),
            meter_value=meter,
            work_order=f"{MARKER}-WO-{idx + 1:02d}",
            workshop=("الورشة الداخلية" if idx % 2 == 0 else "الورشة الخارجية"),
            status="completed",
            is_scheduled=False,
            description=f"صيانة دورية اختبارية للعتاد {idx + 1} — {MARKER}",
        ))
    db.flush()


def _create_technicians_faults_repairs_requests(db: Session, equipment):
    today = date.today()
    technicians = []
    for idx, name in enumerate(("أحمد بن صالح", "محمد قادري", "سمير بوزيد"), start=1):
        tech = Technician(
            employee_number=f"{MARKER}-EMP-{idx:02d}",
            full_name=name,
            specialization=("ميكانيك" if idx == 1 else "كهرباء" if idx == 2 else "هيدروليك"),
            is_active=1,
            notes=f"عامل/فني اختبار {MARKER}",
        )
        db.add(tech)
        technicians.append(tech)
    db.flush()

    faults = []
    repairs = []
    requests = []
    parts = []
    for idx in range(3):
        eq = equipment[idx]
        fault = Fault(
            equipment_id=eq.id,
            reported_date=today - timedelta(days=4),
            report_number=f"{MARKER}-FAULT-{idx + 1:02d}",
            note=f"عطل اختباري مترابط — {MARKER}",
            meter_value=Decimal("1160") + Decimal(idx * 100),
            fault_type=("تبريد" if idx == 0 else "كهرباء" if idx == 1 else "هيدروليك"),
            description=f"وصف عطل اختباري للمعدة {idx + 1}",
            severity=("high" if idx == 0 else "medium"),
            status="repairing",
            exploitation_impact=("limited" if idx < 2 else "prohibited"),
        )
        db.add(fault)
        db.flush()
        repair = Repair(
            fault_id=fault.id,
            repair_date=today - timedelta(days=3),
            meter_value=Decimal("1170") + Decimal(idx * 100),
            diagnosis=f"تشخيص اختباري {MARKER}",
            action_taken=f"إجراء إصلاح اختباري {MARKER}",
            technician=technicians[idx].full_name,
            workshop_type=("external" if idx == 1 else "internal"),
            workshop=("ورشة خارجية تجريبية" if idx == 1 else "الورشة الداخلية"),
            repair_document=f"{MARKER}-REPAIR-{idx + 1:02d}",
            external_dispatch_document=(f"{MARKER}-EXT-{idx + 1:02d}" if idx == 1 else None),
            labor_hours=Decimal("4.5") + Decimal(idx),
            status=("in_progress" if idx < 2 else "completed"),
            notes=f"تصليح اختباري {MARKER}",
        )
        db.add(repair)
        db.flush()
        db.add(TechnicianIntervention(
            repair_id=repair.id,
            technician_id=technicians[idx].id,
            intervention_date=today - timedelta(days=2),
            hours=Decimal("2.5") + Decimal(idx),
            work_description=f"تدخل فني اختباري — {MARKER}",
        ))

        part = SparePart(
            part_number=f"{MARKER}-PART-{idx + 1:02d}",
            name=("فلتر زيت" if idx == 0 else "سير مروحة" if idx == 1 else "مرشح هواء"),
            receiving_document=f"{MARKER}-PART-REC-{idx + 1:02d}",
            notes=f"قطعة غيار اختبارية {MARKER}",
        )
        db.add(part)
        db.flush()
        db.add(RepairPart(
            repair_id=repair.id,
            spare_part_id=part.id,
            quantity=1,
            distribution_document=f"{MARKER}-REPAIR-DIST-{idx + 1:02d}",
            notes=f"استهلاك اختباري — {MARKER}",
        ))

        request = request_services.create_request(
            db,
            SparePartRequestCreate(
                request_number=f"{MARKER}-REQ-{idx + 1:02d}",
                request_date=repair.repair_date,
                received_date=today - timedelta(days=1),
                source_type="repair",
                source_id=repair.id,
                notes=f"طلب غيار اختباري مترابط مع التصليح — {MARKER}",
                items=[
                    SparePartRequestItemCreate(
                        spare_part_id=part.id,
                        requested_quantity=3,
                        received_quantity=3,
                        received_date=today - timedelta(days=1),
                        recipient=WAREHOUSE,
                        supplier_institution=SUPPLIER,
                        notes=f"استلام اختباري كامل — {MARKER}",
                    )
                ],
            ),
        )
        faults.append(fault)
        repairs.append(repair)
        requests.append(request)
        parts.append(part)

    db.flush()
    return technicians, faults, repairs, requests, parts


def _create_movements(db: Session, requests):
    today = date.today()
    distribution_docs = []
    for idx, request in enumerate(requests):
        item = request.items[0]
        doc = movement_services.create_document(
            db,
            MovementDocumentCreate(
                document_number=f"{MARKER}-DIST-{idx + 1:02d}",
                document_type="distribution",
                document_date=today,
                issuer=WAREHOUSE,
                recipient=DISTRIBUTION_RECIPIENT,
                beneficiary=DISTRIBUTION_RECIPIENT,
                notes=f"توزيع اختباري {MARKER}",
                items=[
                    MovementItemCreate(
                        request_item_id=item.id,
                        received_request_item_id=item.id,
                        quantity=Decimal("2"),
                        notes=f"توزيع 2 من 3 — {MARKER}",
                    )
                ],
            ),
        )
        distribution_docs.append(doc)

    return_doc = movement_services.create_document(
        db,
        MovementDocumentCreate(
            document_number=f"{MARKER}-RETURN-01",
            document_type="return",
            document_date=today,
            issuer=WAREHOUSE,
            recipient=SUPPLIER,
            beneficiary=SUPPLIER,
            notes=f"إرجاع اختباري مرتبط مباشرة ببند الاستلام — {MARKER}",
            items=[
                MovementItemCreate(
                    request_item_id=requests[0].items[0].id,
                    received_request_item_id=requests[0].items[0].id,
                    quantity=Decimal("1"),
                    notes=f"إرجاع وحدة واحدة — {MARKER}",
                )
            ],
        ),
    )
    return distribution_docs, return_doc


def _create_missions(db: Session, equipment):
    today = date.today()
    drivers = ("عبد القادر بن علي", "ياسين مرابط", "رشيد بلقاسم")
    for idx in range(3):
        mission_services.add_mission(
            db,
            {
                "equipment_id": equipment[idx].id,
                "driver_name": drivers[idx],
                "mission_document": f"{MARKER}-MISSION-{idx + 1:02d}",
                "purpose": "مهمة اختبارية للبيانات المترابطة",
                "destination": ("سطيف" if idx == 0 else "باتنة" if idx == 1 else "برج بوعريريج"),
                "start_date": today - timedelta(days=20),
                "end_date": today - timedelta(days=15),
                "notes": f"سائق اختباري — {MARKER}",
            },
        )
    mission_services.sync_mission_statuses(db)


def seed(db: Session) -> dict:
    _assert_clean(db)
    categories, brands, types, models, positions, spec_definitions = _create_master_data(db)
    equipment = _create_equipment(db, types, models)
    _create_meters(db, equipment)
    _create_tires_and_batteries(db, equipment, models, positions)
    _create_maintenance(db, equipment, models)
    technicians, faults, repairs, requests, parts = _create_technicians_faults_repairs_requests(db, equipment)
    distribution_docs, return_doc = _create_movements(db, requests)
    _create_missions(db, equipment)
    db.commit()

    return {
        "marker": MARKER,
        "categories": len(categories),
        "types": len(types),
        "models": len(models),
        "equipment": len(equipment),
        "technicians": len(technicians),
        "drivers": 3,
        "tires": db.query(Tire.id).filter(Tire.serial_number.like(f"{MARKER}%")).count(),
        "batteries": db.query(Battery.id).filter(Battery.serial_number.like(f"{MARKER}%")).count(),
        "maintenance_records": db.query(MaintenanceRecord.id).filter(MaintenanceRecord.work_order.like(f"{MARKER}%")).count(),
        "faults": len(faults),
        "repairs": len(repairs),
        "spare_requests": len(requests),
        "distribution_documents": len(distribution_docs),
        "return_documents": 1 if return_doc else 0,
        "meter_readings": db.query(MeterReading.id).filter(MeterReading.source == f"{MARKER}-meter").count(),
    }


def clean(db: Session) -> dict:
    equipment_ids = [
        row[0] for row in db.query(Equipment.id).filter(Equipment.asset_code.like(f"{MARKER}%")).all()
    ]
    tire_ids = [row[0] for row in db.query(Tire.id).filter(Tire.serial_number.like(f"{MARKER}%")).all()]
    battery_ids = [row[0] for row in db.query(Battery.id).filter(Battery.serial_number.like(f"{MARKER}%")).all()]
    fault_ids = [row[0] for row in db.query(Fault.id).filter(Fault.report_number.like(f"{MARKER}%")).all()]
    repair_ids = [row[0] for row in db.query(Repair.id).filter(Repair.repair_document.like(f"{MARKER}%")).all()]
    request_ids = [row[0] for row in db.query(SparePartRequest.id).filter(SparePartRequest.request_number.like(f"{MARKER}%")).all()]
    movement_ids = [row[0] for row in db.query(SparePartMovementDocument.id).filter(SparePartMovementDocument.document_number.like(f"{MARKER}%")).all()]
    technician_ids = [row[0] for row in db.query(Technician.id).filter(Technician.employee_number.like(f"{MARKER}%")).all()]
    maintenance_record_ids = [row[0] for row in db.query(MaintenanceRecord.id).filter(MaintenanceRecord.work_order.like(f"{MARKER}%")).all()]
    plan_ids = [row[0] for row in db.query(MaintenancePlan.id).filter(MaintenancePlan.name.like(f"{MARKER}%")).all()]
    operation_ids = [row[0] for row in db.query(MaintenanceOperation.id).filter(MaintenanceOperation.name.like(f"{MARKER}%")).all()]
    group_ids = [row[0] for row in db.query(MaintenanceOperationGroup.id).filter(MaintenanceOperationGroup.name.like(f"{MARKER}%")).all()]
    model_ids = [row[0] for row in db.query(EquipmentModel.id).filter(EquipmentModel.name.like(f"{MARKER}%")).all()]
    type_ids = [row[0] for row in db.query(EquipmentType.id).filter(EquipmentType.name.like(f"{MARKER}%")).all()]
    category_ids = [row[0] for row in db.query(EquipmentCategory.id).filter(EquipmentCategory.code.like(f"{MARKER}%")).all()]
    brand_ids = [row[0] for row in db.query(EquipmentBrand.id).filter(EquipmentBrand.name.like(f"{MARKER}%")).all()]
    spec_ids = [row[0] for row in db.query(EquipmentModelSpecDefinition.id).filter(EquipmentModelSpecDefinition.code.like(f"{MARKER}%")).all()]
    part_ids = [row[0] for row in db.query(SparePart.id).filter(SparePart.part_number.like(f"{MARKER}%")).all()]

    if not any((equipment_ids, tire_ids, battery_ids, fault_ids, repair_ids, request_ids, movement_ids, technician_ids, maintenance_record_ids, plan_ids, operation_ids, group_ids, model_ids, type_ids, category_ids, brand_ids, spec_ids, part_ids)):
        return {"marker": MARKER, "deleted": 0}

    if movement_ids:
        db.query(SparePartMovementItem).filter(SparePartMovementItem.document_id.in_(movement_ids)).delete(synchronize_session=False)
        db.query(SparePartMovementDocument).filter(SparePartMovementDocument.id.in_(movement_ids)).delete(synchronize_session=False)

    if request_ids:
        db.query(SparePartRequest).filter(SparePartRequest.id.in_(request_ids)).delete(synchronize_session=False)

    if repair_ids:
        db.query(RepairPart).filter(RepairPart.repair_id.in_(repair_ids)).delete(synchronize_session=False)
        db.query(TechnicianIntervention).filter(TechnicianIntervention.repair_id.in_(repair_ids)).delete(synchronize_session=False)
        db.query(Repair).filter(Repair.id.in_(repair_ids)).delete(synchronize_session=False)

    if fault_ids:
        db.query(Fault).filter(Fault.id.in_(fault_ids)).delete(synchronize_session=False)

    if maintenance_record_ids:
        db.query(MaintenanceRecord).filter(MaintenanceRecord.id.in_(maintenance_record_ids)).delete(synchronize_session=False)
    if plan_ids:
        db.query(MaintenancePlanOperation).filter(MaintenancePlanOperation.plan_id.in_(plan_ids)).delete(synchronize_session=False)
        db.query(MaintenancePlan).filter(MaintenancePlan.id.in_(plan_ids)).delete(synchronize_session=False)
    if operation_ids:
        db.query(MaintenanceOperation).filter(MaintenanceOperation.id.in_(operation_ids)).delete(synchronize_session=False)
    if group_ids:
        db.query(MaintenanceOperationGroup).filter(MaintenanceOperationGroup.id.in_(group_ids)).delete(synchronize_session=False)

    if equipment_ids:
        db.query(MeterReadingChange).filter(MeterReadingChange.equipment_id.in_(equipment_ids)).delete(synchronize_session=False)
        db.query(MeterReading).filter(MeterReading.equipment_id.in_(equipment_ids)).delete(synchronize_session=False)
        db.query(Mission).filter(Mission.equipment_id.in_(equipment_ids)).delete(synchronize_session=False)

    if technician_ids:
        db.query(Technician).filter(Technician.id.in_(technician_ids)).delete(synchronize_session=False)

    if tire_ids:
        db.query(TireDisposal).filter(TireDisposal.tire_id.in_(tire_ids)).delete(synchronize_session=False)
        db.query(Tire).filter(Tire.id.in_(tire_ids)).delete(synchronize_session=False)

    if battery_ids:
        db.query(BatteryMovement).filter(BatteryMovement.battery_id.in_(battery_ids)).delete(synchronize_session=False)
        db.query(Battery).filter(Battery.id.in_(battery_ids)).delete(synchronize_session=False)

    if part_ids:
        db.query(SparePart).filter(SparePart.id.in_(part_ids)).delete(synchronize_session=False)

    if equipment_ids:
        db.query(Equipment).filter(Equipment.id.in_(equipment_ids)).delete(synchronize_session=False)

    if model_ids:
        db.query(EquipmentModelSpecValue).filter(EquipmentModelSpecValue.equipment_model_id.in_(model_ids)).delete(synchronize_session=False)
        db.query(TireModelSize).filter(TireModelSize.equipment_model_id.in_(model_ids)).delete(synchronize_session=False)
        db.query(TirePosition).filter(TirePosition.equipment_model_id.in_(model_ids)).delete(synchronize_session=False)
        db.query(EquipmentModel).filter(EquipmentModel.id.in_(model_ids)).delete(synchronize_session=False)

    if spec_ids:
        db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.id.in_(spec_ids)).delete(synchronize_session=False)

    if brand_ids:
        db.query(EquipmentBrand).filter(EquipmentBrand.id.in_(brand_ids)).delete(synchronize_session=False)
    if type_ids:
        db.query(EquipmentType).filter(EquipmentType.id.in_(type_ids)).delete(synchronize_session=False)
    if category_ids:
        db.query(EquipmentCategory).filter(EquipmentCategory.id.in_(category_ids)).delete(synchronize_session=False)

    db.commit()
    return {"marker": MARKER, "deleted": 1}


def main() -> None:
    parser = argparse.ArgumentParser(description="بيانات اختبار Materiel قابلة للإضافة والحذف الآمن.")
    parser.add_argument("action", choices=("seed", "clean"))
    parser.add_argument("--database-url", default=None, help="مثل sqlite:///./fleet_assets.db")
    args = parser.parse_args()

    _, SessionLocal = _session(args.database_url)
    db = SessionLocal()
    try:
        result = seed(db) if args.action == "seed" else clean(db)
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
