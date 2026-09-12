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


def _installed_battery_count(db: Session, equipment_id: int, exclude_battery_id: int | None = None) -> int:
    """Count batteries currently installed on an equipment item.

    The allowed quantity comes from the equipment model in Master Data.
    This keeps battery capacity rules centralized at model level instead of
    asking the user to configure the same quantity for every vehicle.
    """
    count = 0
    for battery in db.query(Battery).all():
        if exclude_battery_id is not None and battery.id == exclude_battery_id:
            continue
        state = current_state(db, battery.id)
        if state and state["installed"] and state["equipment"] and state["equipment"].id == equipment_id:
            count += 1
    return count


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
        equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if not equipment:
            raise ValueError("العتاد غير موجود")

        # Master Data rule: a model defines how many batteries its equipment
        # is designed to carry. Keep legacy models without a configured count
        # at the existing one-battery limit.
        required_count = getattr(equipment.equipment_model, "battery_count_required", None) or 1
        installed_count = _installed_battery_count(db, equipment_id, exclude_battery_id=battery.id)
        if installed_count >= required_count:
            if required_count == 1:
                raise ValueError("العتاد لديه بطارية مركبة بالفعل")
            raise ValueError(f"العتاد وصل إلى العدد المسموح به من البطاريات لهذا الطراز ({required_count})")
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
    if not state:
        return "unassigned"

    # current_state() supplies the movement object, while lightweight callers
    # and existing tests may provide only the derived installed flag. Support
    # both representations without changing the source-of-truth model.
    movement = state.get("movement") if isinstance(state, dict) else None
    if movement and movement.movement_type == "remove":
        reason = (movement.reason or "").strip().lower()
        if reason in {"تالف", "damaged", "تلف"}:
            return "damaged"
        if reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
            return "expired"

    if state.get("installed"):
        return "installed"
    return "stock"


def stats(db: Session):
    counts = {"total": 0, "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "unassigned": 0}
    for battery in list_batteries(db):
        counts["total"] += 1
        key = status(battery, current_state(db, battery.id))
        counts[key] += 1
    return counts
