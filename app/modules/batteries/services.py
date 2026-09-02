from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.batteries.models import Battery, BatteryMovement, BatteryPosition

MOVEMENT_TYPES = {"install", "remove", "move"}


def list_batteries(db: Session):
    return db.query(Battery).order_by(Battery.serial_number).all()


def list_positions(db: Session):
    return db.query(BatteryPosition).order_by(BatteryPosition.sort_order, BatteryPosition.id).all()


def get_battery(db: Session, battery_id: int):
    return db.query(Battery).filter(Battery.id == battery_id).first()


def history(db: Session, battery_id: int):
    return db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.asc(), BatteryMovement.id.asc()).all()


def current_state(db: Session, battery_id: int):
    movements = history(db, battery_id)
    state = None
    for movement in movements:
        if movement.movement_type == "remove":
            state = {"movement": movement, "installed": False, "equipment": None}
        else:
            state = {"movement": movement, "installed": True, "equipment": movement.equipment}
    return state


def _validate_meter(db: Session, equipment_id: int, movement_date: date, meter_value: Decimal | None):
    if meter_value is None:
        return
    from app.modules.meter_readings.models import MeterReading
    readings = db.query(MeterReading).filter(MeterReading.equipment_id == equipment_id).order_by(MeterReading.reading_date.asc(), MeterReading.id.asc()).all()
    before = [r for r in readings if r.reading_date.date() <= movement_date and (r.odometer is not None or r.hours is not None)]
    after = [r for r in readings if r.reading_date.date() >= movement_date and (r.odometer is not None or r.hours is not None)]
    if before:
        value = before[-1].odometer if before[-1].odometer is not None else before[-1].hours
        if meter_value < value:
            raise ValueError("قراءة العداد أقل من آخر قراءة معروفة قبل هذا التاريخ")
    if after:
        value = after[0].odometer if after[0].odometer is not None else after[0].hours
        if meter_value > value:
            raise ValueError("قراءة العداد أكبر من أول قراءة معروفة بعد هذا التاريخ")


def validate_movement(db: Session, battery: Battery, movement_type: str, movement_date: date, equipment_id: int | None, meter_value: Decimal | None):
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("نوع حركة البطارية غير صالح")
    if movement_date > date.today():
        raise ValueError("لا يمكن تسجيل حركة بتاريخ مستقبلي")
    state = current_state(db, battery.id)
    if movement_type == "install":
        if state and state["installed"]:
            raise ValueError("البطارية مركبة بالفعل")
        if equipment_id is None:
            raise ValueError("العتاد مطلوب عند التركيب")
    elif movement_type == "remove":
        if not state or not state["installed"]:
            raise ValueError("لا يمكن فك بطارية غير مركبة")
    elif movement_type == "move":
        if not state or not state["installed"]:
            raise ValueError("لا يمكن نقل بطارية غير مركبة")
        if equipment_id is None:
            raise ValueError("العتاد مطلوب عند النقل")
    if equipment_id is not None:
        _validate_meter(db, equipment_id, movement_date, meter_value)


def add_battery(db: Session, data: dict):
    battery = Battery(**data)
    db.add(battery)
    db.commit()
    db.refresh(battery)
    return battery


def add_position(db: Session, data: dict):
    position = BatteryPosition(**data)
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def add_movement(db: Session, battery_id: int, data: dict):
    battery = get_battery(db, battery_id)
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
    if state and state.get("installed"):
        return "installed"
    if state:
        return "stock"
    return "unassigned"


def stats(db: Session):
    counts = {"total": 0, "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "unassigned": 0}
    for battery in list_batteries(db):
        counts["total"] += 1
        key = status(battery, current_state(db, battery.id))
        counts[key] = counts.get(key, 0) + 1
    return counts


def inventory(db: Session):
    result = []
    for battery in list_batteries(db):
        state = current_state(db, battery.id)
        if not state or not state["installed"]:
            result.append({"battery": battery, "state": state, "status": status(battery, state)})
    return result


def installed_for_equipment(db: Session, equipment_id: int):
    return [
        {"battery": battery, "state": state}
        for battery in list_batteries(db)
        for state in [current_state(db, battery.id)]
        if state and state["installed"] and state["equipment"] and state["equipment"].id == equipment_id
    ]
