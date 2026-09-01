from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.equipment.models import Equipment
from app.modules.fuel.models import FuelRecord

ABNORMAL_FACTOR = Decimal("1.20")


def list_records(db: Session):
    return db.query(FuelRecord).order_by(FuelRecord.fueling_date.desc(), FuelRecord.id.desc()).all()


def _previous(db: Session, equipment_id: int, fueling_date: date, record_id: int | None = None):
    q = db.query(FuelRecord).filter(FuelRecord.equipment_id == equipment_id)
    if record_id:
        q = q.filter(FuelRecord.id != record_id)
    return q.order_by(FuelRecord.fueling_date.desc(), FuelRecord.meter_value.desc(), FuelRecord.id.desc()).first()


def validate_record(db: Session, equipment_id: int, fueling_date: date, meter_value: Decimal, quantity: Decimal, record_id: int | None = None):
    if fueling_date > date.today():
        raise ValueError("لا يمكن تسجيل تعبئة بتاريخ مستقبلي")
    if meter_value < 0 or quantity <= 0:
        raise ValueError("العداد والكمية يجب أن تكونا موجبتين")
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise ValueError("العتاد غير موجود")
    if equipment.current_odometer is not None and meter_value > equipment.current_odometer:
        raise ValueError("قراءة العداد أعلى من العداد الحالي للعتاد")
    previous = _previous(db, equipment_id, fueling_date, record_id)
    if previous:
        if fueling_date < previous.fueling_date:
            raise ValueError("تاريخ التعبئة لا يمكن أن يسبق آخر تعبئة")
        if meter_value < previous.meter_value:
            raise ValueError("قراءة العداد لا يمكن أن تقل عن القراءة السابقة")
    return previous


def add_record(db: Session, data: dict):
    previous = validate_record(db, data["equipment_id"], data["fueling_date"], data["meter_value"], data["quantity"])
    if data.get("sequence_number") is None:
        data["sequence_number"] = (db.query(func.max(FuelRecord.sequence_number)).filter(FuelRecord.equipment_id == data["equipment_id"]).scalar() or 0) + 1
    record = FuelRecord(**data)
    db.add(record)
    db.commit(); db.refresh(record)
    return record


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


def monthly_summary(db: Session):
    rows = []
    for record in list_records(db):
        key = (record.fueling_date.year, record.fueling_date.month)
        found = next((x for x in rows if x["year"] == key[0] and x["month"] == key[1]), None)
        if not found:
            found = {"year": key[0], "month": key[1], "quantity": Decimal("0"), "records": 0}
            rows.append(found)
        found["quantity"] += Decimal(record.quantity)
        found["records"] += 1
    return sorted(rows, key=lambda x: (x["year"], x["month"]), reverse=True)
