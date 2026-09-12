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


def _state_from_history(movements):
    state = {"installed": False, "equipment_id": None, "movement": None}
    for movement in sorted(movements, key=lambda m: (m.movement_date, m.id)):
        if movement.movement_type == "remove":
            state = {"installed": False, "equipment_id": None, "movement": movement}
        elif movement.movement_type in {"install", "move"}:
            state = {"installed": True, "equipment_id": movement.equipment_id, "movement": movement}
    return state


def _state_at(db: Session, battery_id: int, when: date, extra=None):
    movements = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id, BatteryMovement.movement_date <= when).all()
    if extra is not None:
        movements.append(extra)
    return _state_from_history(movements)


def _installed_battery_count(db: Session, equipment_id: int, exclude_battery_id: int | None = None, when: date | None = None) -> int:
    """Count batteries installed on equipment at a point in history."""
    count = 0
    for battery in db.query(Battery).all():
        if exclude_battery_id is not None and battery.id == exclude_battery_id:
            continue
        state = _state_at(db, battery.id, when) if when is not None else current_state(db, battery.id)
        if state and state["installed"] and state["equipment_id"] == equipment_id:
            count += 1
    return count


def _validate_meter_history(movements):
    previous_equipment_id = None
    previous = None
    for movement in sorted(movements, key=lambda m: (m.movement_date, m.id)):
        if movement.movement_type == "remove":
            previous_equipment_id = None
            previous = None
            continue
        if movement.meter_value is None or movement.equipment_id is None:
            continue
        value = Decimal(str(movement.meter_value))
        if previous_equipment_id == movement.equipment_id and previous is not None and value < previous:
            raise ValueError("قراءات عداد حركات البطارية غير متوافقة مع التسلسل الزمني للعتاد")
        previous_equipment_id = movement.equipment_id
        previous = value


def _validate_equipment_meter(db: Session, equipment_id: int, movement_date: date, meter_value: Decimal | None):
    if meter_value is None:
        return
    readings = []
    # Keep the check historical: only readings on or around the movement date
    # constrain a backdated movement; the current odometer remains a present-day upper bound.
    from app.modules.meter_readings.models import MeterReading
    rows = db.query(MeterReading).filter(MeterReading.equipment_id == equipment_id).order_by(MeterReading.reading_date.asc(), MeterReading.id.asc()).all()
    for reading in rows:
        value = reading.odometer if reading.odometer is not None else reading.hours
        if value is not None:
            reading_date = reading.reading_date.date() if hasattr(reading.reading_date, "date") else reading.reading_date
            readings.append((reading_date, Decimal(str(value))))
    before = [value for d, value in readings if d <= movement_date]
    after = [value for d, value in readings if d >= movement_date]
    if before and meter_value < before[-1]:
        raise ValueError("قراءة العداد أقل من آخر قراءة معروفة للعتاد قبل هذا التاريخ")
    if after and meter_value > after[0]:
        raise ValueError("قراءة العداد أكبر من أول قراءة معروفة للعتاد بعد هذا التاريخ")
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if equipment and equipment.current_odometer is not None and meter_value > equipment.current_odometer:
        raise ValueError("قراءة العداد أعلى من العداد الحالي للعتاد")


def validate_movement(db: Session, battery: Battery, movement_type: str, movement_date: date, equipment_id: int | None, meter_value: Decimal | None):
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("نوع حركة البطارية غير صالح")
    if movement_date > date.today():
        raise ValueError("لا يمكن تسجيل حركة بتاريخ مستقبلي")
    if db is None:
        if movement_type in {"install", "move"} and not equipment_id:
            raise ValueError("العتاد مطلوب عند تركيب أو نقل البطارية")
        return

    existing = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery.id).order_by(BatteryMovement.movement_date.asc(), BatteryMovement.id.asc()).all()
    synthetic_id = max((m.id for m in existing), default=0) + 1
    candidate = BatteryMovement(id=synthetic_id, battery_id=battery.id, movement_date=movement_date, movement_type=movement_type, equipment_id=equipment_id, meter_value=meter_value)
    timeline = sorted(existing + [candidate], key=lambda m: (m.movement_date, m.id))
    _validate_meter_history(timeline)

    state_at = {"installed": False, "equipment_id": None}
    for movement in timeline:
        if movement.movement_type == "install":
            if state_at["installed"]:
                raise ValueError("التسلسل التاريخي غير صالح: البطارية مركبة بالفعل قبل عملية التركيب")
            if not movement.equipment_id:
                raise ValueError("العتاد مطلوب عند التركيب")
            if battery.expiry_date and movement.movement_date > battery.expiry_date:
                raise ValueError("لا يمكن تركيب بطارية منتهية الصلاحية في تاريخ الحركة المحدد")
            equipment = db.query(Equipment).filter(Equipment.id == movement.equipment_id).first()
            if not equipment:
                raise ValueError("العتاد غير موجود")
            required_count = getattr(equipment.equipment_model, "battery_count_required", None) or 1
            installed_count = _installed_battery_count(db, equipment.id, exclude_battery_id=battery.id, when=movement.movement_date)
            if installed_count >= required_count:
                if required_count == 1:
                    raise ValueError("العتاد لديه بطارية مركبة بالفعل في التاريخ المحدد")
                raise ValueError(f"العتاد وصل إلى العدد المسموح به من البطاريات لهذا الطراز ({required_count}) في التاريخ المحدد")
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            state_at = {"installed": True, "equipment_id": movement.equipment_id}
        elif movement.movement_type == "move":
            if not state_at["installed"]:
                raise ValueError("لا يمكن نقل بطارية غير مركبة في التاريخ المحدد")
            if not movement.equipment_id:
                raise ValueError("العتاد مطلوب عند النقل")
            if battery.expiry_date and movement.movement_date > battery.expiry_date:
                raise ValueError("لا يمكن نقل بطارية منتهية الصلاحية في تاريخ الحركة المحدد")
            equipment = db.query(Equipment).filter(Equipment.id == movement.equipment_id).first()
            if not equipment:
                raise ValueError("العتاد غير موجود")
            required_count = getattr(equipment.equipment_model, "battery_count_required", None) or 1
            installed_count = _installed_battery_count(db, equipment.id, exclude_battery_id=battery.id, when=movement.movement_date)
            if installed_count >= required_count and movement.equipment_id != state_at["equipment_id"]:
                raise ValueError(f"العتاد وصل إلى العدد المسموح به من البطاريات لهذا الطراز ({required_count}) في التاريخ المحدد")
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            state_at = {"installed": True, "equipment_id": movement.equipment_id}
        elif movement.movement_type == "remove":
            if not state_at["installed"]:
                raise ValueError("لا يمكن فك بطارية غير مركبة في التاريخ المحدد")
            state_at = {"installed": False, "equipment_id": None}


def add_battery(db: Session, data: dict):
    data = dict(data)
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
