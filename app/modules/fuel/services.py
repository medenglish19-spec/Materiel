from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel
from app.modules.fuel.models import FuelRecord
from app.modules.meter_readings.services import sync_current_meter, validate_meter_observation
from app.modules.meter_readings.models import MeterReading

ABNORMAL_FACTOR = Decimal("1.20")


def list_records(db: Session):
    return db.query(FuelRecord).options(
        joinedload(FuelRecord.equipment)
        .joinedload(Equipment.equipment_model)
        .joinedload(EquipmentModel.brand)
    ).order_by(
        FuelRecord.fueling_date.desc(), FuelRecord.id.desc()
    ).all()


def _previous(db: Session, equipment_id: int, fueling_date: date, record_id: int | None = None):
    q = db.query(FuelRecord).filter(FuelRecord.equipment_id == equipment_id)
    if record_id:
        q = q.filter(
            or_(
                FuelRecord.fueling_date < fueling_date,
                and_(
                    FuelRecord.fueling_date == fueling_date,
                    FuelRecord.id < record_id,
                ),
            )
        )
    else:
        q = q.filter(FuelRecord.fueling_date < fueling_date)
    return q.order_by(FuelRecord.fueling_date.desc(), FuelRecord.id.desc()).first()


def validate_record(db: Session, equipment_id: int, fueling_date: date, meter_value: Decimal, quantity: Decimal, record_id: int | None = None):
    if fueling_date > date.today():
        raise ValueError("لا يمكن تسجيل تعبئة بتاريخ مستقبلي")
    if meter_value < 0 or quantity <= 0:
        raise ValueError("العداد والكمية يجب أن تكونا موجبتين")
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise ValueError("العتاد غير موجود")
    unit = (equipment.equipment_type.measurement_unit if equipment.equipment_type else "km")
    reference = f"fuel:{record_id}:meter" if record_id is not None else None
    validate_meter_observation(db, equipment_id, fueling_date, meter_value, unit, "الوقود", source_reference=reference)
    return _previous(db, equipment_id, fueling_date, record_id)


def add_record(db: Session, data: dict):
    previous = validate_record(db, data["equipment_id"], data["fueling_date"], data["meter_value"], data["quantity"])
    if data.get("sequence_number") is None:
        data["sequence_number"] = (db.query(func.max(FuelRecord.sequence_number)).filter(FuelRecord.equipment_id == data["equipment_id"]).scalar() or 0) + 1
    record = FuelRecord(**data)
    db.add(record)
    db.flush()
    sync_current_meter(db, record.equipment_id)
    db.commit(); db.refresh(record)
    return record


def update_record(db: Session, record_id: int, data: dict):
    record = db.query(FuelRecord).filter(FuelRecord.id == record_id).first()
    if record is None:
        raise ValueError("سجل التعبئة غير موجود")
    validate_record(
        db, record.equipment_id, data["fueling_date"], data["meter_value"],
        data["quantity"], record_id=record.id,
    )
    record.fueling_date = data["fueling_date"]
    record.meter_value = data["meter_value"]
    record.quantity = data["quantity"]
    record.fuel_type = data.get("fuel_type")
    record.document_number = data.get("document_number")
    record.station = data.get("station")
    record.notes = data.get("notes")
    db.commit()
    sync_current_meter(db, record.equipment_id)
    db.refresh(record)
    return record


def delete_records(db: Session, record_ids: list[int]):
    unique_ids = set(record_ids)
    records = db.query(FuelRecord).filter(FuelRecord.id.in_(unique_ids)).all() if unique_ids else []
    if len(records) != len(unique_ids):
        raise ValueError("تعذر حذف سجلات الوقود المحددة؛ قد يكون أحد السجلات غير موجود")
    equipment_ids = {record.equipment_id for record in records}
    for record in records:
        db.delete(record)
    db.flush()
    for equipment_id in equipment_ids:
        sync_current_meter(db, equipment_id)
    db.commit()
    return len(records)


def distance_from_previous(db: Session, record: FuelRecord):
    previous = _previous(db, record.equipment_id, record.fueling_date, record.id)
    if not previous:
        return None
    distance = Decimal(record.meter_value) - Decimal(previous.meter_value)
    return distance if distance >= 0 else None


def consumption(db: Session, record: FuelRecord):
    distance = distance_from_previous(db, record)
    if not distance or distance <= 0:
        return None
    return (Decimal(record.quantity) * Decimal(100) / distance).quantize(Decimal("0.01"))


def equipment_average(db: Session, equipment_id: int):
    values = []
    for record in db.query(FuelRecord).filter(FuelRecord.equipment_id == equipment_id).order_by(FuelRecord.fueling_date, FuelRecord.id).all():
        value = consumption(db, record)
        if value is not None:
            values.append(value)
    if not values:
        return None
    return (sum(values) / Decimal(len(values))).quantize(Decimal("0.01"))


def is_abnormal(db: Session, record: FuelRecord):
    value = consumption(db, record)
    avg = equipment_average(db, record.equipment_id)
    return bool(value is not None and avg is not None and value > avg * ABNORMAL_FACTOR)


def enrich_records(db: Session, records: list[FuelRecord]) -> tuple[list[dict], dict[int, Decimal | None]]:
    if not records:
        return [], {}

    references = [f"fuel:{record.id}:meter" for record in records if record.id is not None]
    meter_values = {}
    for start in range(0, len(references), 500):
        rows = db.query(
            MeterReading.source_reference, MeterReading.odometer, MeterReading.hours
        ).filter(
            MeterReading.source_reference.in_(references[start : start + 500])
        ).all()
        meter_values.update({
            reference: odometer if odometer is not None else hours
            for reference, odometer, hours in rows
        })

    grouped: dict[int, list[FuelRecord]] = {}
    for record in records:
        grouped.setdefault(record.equipment_id, []).append(record)

    metrics: dict[int, tuple[Decimal | None, Decimal | None, Decimal | None]] = {}
    averages: dict[int, Decimal | None] = {}
    for equipment_id, equipment_records in grouped.items():
        ordered = sorted(
            equipment_records,
            key=lambda record: (record.fueling_date, record.id or 0),
        )
        values: list[Decimal] = []
        previous: FuelRecord | None = None
        for record in ordered:
            value = meter_values.get(f"fuel:{record.id}:meter")
            if value is None:
                value = record.meter_value
            distance = None
            rate = None
            if previous is not None:
                previous_value = meter_values.get(f"fuel:{previous.id}:meter")
                if previous_value is None:
                    previous_value = previous.meter_value
                difference = Decimal(value) - Decimal(previous_value)
                if difference >= 0:
                    distance = difference
                    if distance > 0:
                        rate = (
                            Decimal(record.quantity) * Decimal(100) / distance
                        ).quantize(Decimal("0.01"))
                        values.append(rate)
            metrics[record.id] = (value, distance, rate)
            previous = record

        average = (
            (sum(values) / Decimal(len(values))).quantize(Decimal("0.01"))
            if values else None
        )
        averages[equipment_id] = average

    enriched = []
    for record in records:
        meter_value, distance, rate = metrics[record.id]
        average = averages[record.equipment_id]
        enriched.append({
            "record": record,
            "meter_value": meter_value,
            "distance": distance,
            "consumption": rate,
            "abnormal": bool(
                rate is not None
                and average is not None
                and rate > average * ABNORMAL_FACTOR
            ),
        })
    return enriched, averages


def monthly_summary(db: Session, records: list[FuelRecord] | None = None):
    rows = []
    for record in records if records is not None else list_records(db):
        key = (record.fueling_date.year, record.fueling_date.month)
        found = next((x for x in rows if x["year"] == key[0] and x["month"] == key[1]), None)
        if not found:
            found = {"year": key[0], "month": key[1], "quantity": Decimal("0"), "records": 0}
            rows.append(found)
        found["quantity"] += Decimal(record.quantity)
        found["records"] += 1
    return sorted(rows, key=lambda x: (x["year"], x["month"]), reverse=True)
