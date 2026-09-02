from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.equipment.models import Equipment

MOVEMENT_TYPES = {"install", "move", "remove"}


def list_batteries(db: Session):
    return db.query(Battery).order_by(Battery.serial_number).all()


def current_state(db: Session, battery_id: int):
    movement = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).first()
    if not movement:
        return None
    return {"movement": movement, "installed": movement.movement_type in {"install", "move"} and movement.equipment_id is not None, "equipment": movement.equipment}


def validate_movement(db: Session, battery: Battery, movement_type: str, movement_date: date, equipment_id: int | None, meter_value: Decimal | None):
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("نوع حركة البطارية غير صالح")
    if movement_date > date.today():
        raise ValueError("لا يمكن تسجيل حركة بتاريخ مستقبلي")
    state = current_state(db, battery.id)
    installed = bool(state and state["installed"])
    if movement_type == "install" and installed:
        raise ValueError("البطارية مركبة بالفعل")
    if movement_type in {"move", "remove"} and not installed:
        raise ValueError("لا يمكن نقل أو فك بطارية غير مركبة")
    if movement_type in {"install", "move"}:
        if not equipment_id:
            raise ValueError("العتاد مطلوب عند تركيب أو نقل البطارية")
        if not db.query(Equipment).filter(Equipment.id == equipment_id).first():
            raise ValueError("العتاد غير موجود")
        occupied = db.query(BatteryMovement).filter(BatteryMovement.equipment_id == equipment_id).all()
        for row in occupied:
            if row.battery_id == battery.id:
                continue
            other = current_state(db, row.battery_id)
            if other and other["installed"] and other["equipment"] and other["equipment"].id == equipment_id:
                raise ValueError("العتاد لديه بطارية مركبة بالفعل")
    else:
        equipment_id = None
    last = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery.id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).first()
    if last and movement_date < last.movement_date:
        raise ValueError("تاريخ الحركة لا يمكن أن يسبق آخر حركة")
    if meter_value is not None and last and last.meter_value is not None and meter_value < last.meter_value:
        raise ValueError("قراءة العداد لا يمكن أن تقل عن القراءة السابقة")
    if movement_type in {"install", "move"} and equipment_id:
        equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if meter_value is not None and equipment.current_odometer is not None and meter_value > equipment.current_odometer:
            raise ValueError("قراءة العداد أعلى من العداد الحالي للعتاد")


def add_battery(db: Session, data: dict):
    data = dict(data)
    # Excel logic: default service life is 2 years, calculated from manufacture
    # date, or from receipt date when manufacture date is unavailable.
    if data.get("expiry_date") is None:
        base = data.get("manufacture_date") or data.get("receipt_date")
        if base:
            try:
                from dateutil.relativedelta import relativedelta
                data["expiry_date"] = base + relativedelta(years=2)
            except Exception:
                data["expiry_date"] = date(base.year + 2, base.month, base.day)
    battery = Battery(**data)
    db.add(battery)
    db.commit()
    db.refresh(battery)
    return battery


def add_movement(db: Session, battery_id: int, data: dict):
    battery = db.query(Battery).filter(Battery.id == battery_id).first()
    if not battery:
        raise ValueError("البطارية غير موجودة")
    validate_movement(db, battery, data["movement_type"], data["movement_date"], data.get("equipment_id"), data.get("meter_value"))
    if data["movement_type"] == "remove":
        data["equipment_id"] = None
    movement = BatteryMovement(battery_id=battery_id, **data)
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def status(battery: Battery, state):
    if battery.expiry_date and battery.expiry_date < date.today():
        return "expired"
    movement = state.get("movement") if state else None
    if movement and movement.movement_type == "remove":
        reason = (movement.reason or "").strip().lower()
        if reason in {"تالف", "damaged", "تلف"}:
            return "damaged"
        if reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
            return "expired"
    if state and state["installed"]:
        return "installed"
    if state:
        return "stock"
    return "unassigned"


def stats(db: Session):
    counts = {"total": 0, "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "unassigned": 0}
    for battery in list_batteries(db):
        counts["total"] += 1
        key = status(battery, current_state(db, battery.id))
        counts[key] += 1
    return counts
