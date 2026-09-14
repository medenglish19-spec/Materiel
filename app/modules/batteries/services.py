import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.modules.batteries.models import Battery, BatteryMovement, BatterySystemSetting
from app.modules.equipment.models import Equipment

MOVEMENT_TYPES = {"install", "move", "remove"}


def _add_years(value: date, years: int) -> date:
    day = min(value.day, calendar.monthrange(value.year + years, value.month)[1])
    return date(value.year + years, value.month, day)


def get_validity_years(db: Session) -> int:
    setting = db.query(BatterySystemSetting).filter(BatterySystemSetting.id == 1).first()
    if setting is None:
        setting = BatterySystemSetting(id=1, validity_years=2)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting.validity_years


def set_validity_years(db: Session, years: int):
    if years < 1 or years > 100:
        raise ValueError("مدة صلاحية البطاريات يجب أن تكون بين سنة واحدة و100 سنة")
    setting = db.query(BatterySystemSetting).filter(BatterySystemSetting.id == 1).first()
    if setting is None:
        setting = BatterySystemSetting(id=1, validity_years=years)
        db.add(setting)
    else:
        setting.validity_years = years
    db.commit()
    db.refresh(setting)
    return setting


def list_batteries(db: Session):
    return db.query(Battery).order_by(Battery.serial_number).all()


def current_states(db: Session):
    """Load the latest state of every battery with one movement query."""
    batteries = list_batteries(db)
    movements = (
        db.query(BatteryMovement)
        .options(joinedload(BatteryMovement.equipment))
        .order_by(BatteryMovement.battery_id.asc(), BatteryMovement.movement_date.asc(), BatteryMovement.id.asc())
        .all()
    )
    grouped = {battery.id: [] for battery in batteries}
    for movement in movements:
        if movement.battery_id in grouped:
            grouped[movement.battery_id].append(movement)

    states = {}
    for battery in batteries:
        state = None
        for movement in grouped[battery.id]:
            if movement.movement_type == "remove":
                state = {"movement": movement, "installed": False, "equipment": None}
            else:
                state = {
                    "movement": movement,
                    "installed": movement.equipment_id is not None,
                    "equipment": movement.equipment,
                }
        states[battery.id] = state
    return batteries, states


def current_state(db: Session, battery_id: int):
    movement = db.query(BatteryMovement).options(joinedload(BatteryMovement.equipment)).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).first()
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
    batteries = db.query(Battery).all()
    if when is None:
        _, states = current_states(db)
        for battery in batteries:
            if exclude_battery_id is not None and battery.id == exclude_battery_id:
                continue
            state = states.get(battery.id)
            if state and state["installed"] and state["equipment"].id == equipment_id:
                count += 1
        return count

    movements = db.query(BatteryMovement).filter(BatteryMovement.movement_date <= when).order_by(BatteryMovement.battery_id.asc(), BatteryMovement.movement_date.asc(), BatteryMovement.id.asc()).all()
    grouped = {battery.id: [] for battery in batteries}
    for movement in movements:
        if movement.battery_id in grouped:
            grouped[movement.battery_id].append(movement)
    for battery in batteries:
        if exclude_battery_id is not None and battery.id == exclude_battery_id:
            continue
        state = _state_from_history(grouped[battery.id])
        if state["installed"] and state["equipment_id"] == equipment_id:
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


def _equipment_age_below_limit(equipment: Equipment | None, when: date, years: int) -> bool:
    first_service = getattr(equipment, "first_service_date", None) if equipment else None
    return bool(first_service and when < _add_years(first_service, years))


def _general_expiry_date(battery: Battery, years: int) -> date | None:
    base = battery.manufacture_date or battery.receipt_date
    return _add_years(base, years) if base else None


def _expired_at(db: Session, battery: Battery, equipment: Equipment | None, when: date) -> bool:
    years = get_validity_years(db)
    if equipment and getattr(equipment, "first_service_date", None):
        return when >= _add_years(equipment.first_service_date, years)
    expiry = _general_expiry_date(battery, years)
    return bool(expiry and when >= expiry)


def replacement_due_date(db: Session, battery: Battery, equipment: Equipment | None = None) -> date | None:
    years = get_validity_years(db)
    if equipment and getattr(equipment, "first_service_date", None):
        return _add_years(equipment.first_service_date, years)
    return _general_expiry_date(battery, years)


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
            equipment = db.query(Equipment).filter(Equipment.id == movement.equipment_id).first()
            if not equipment:
                raise ValueError("العتاد غير موجود")
            # replacement_due_date is advisory only. A battery remains usable
            # after the estimated replacement date until it is explicitly
            # reported as damaged/unusable. Therefore it must never block an
            # install or move merely because its estimated date has passed.
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
            equipment = db.query(Equipment).filter(Equipment.id == movement.equipment_id).first()
            if not equipment:
                raise ValueError("العتاد غير موجود")
            # Estimated replacement date is not a technical failure state and
            # therefore does not prevent transferring a still-serviceable battery.
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
    data.pop("expiry_date", None)
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


def status(battery: Battery, state, equipment: Equipment | None = None, db: Session | None = None):
    movement = state.get("movement") if isinstance(state, dict) else None
    if movement and movement.movement_type == "remove":
        reason = (movement.reason or "").strip().lower()
        if reason in {"تالف", "damaged", "تلف"}:
            return "damaged"
        if reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
            return "expired"
    if db is not None and state and state.get("installed"):
        target = equipment or state.get("equipment")
        if _expired_at(db, battery, target, date.today()):
            return "expired"
    elif db is None and battery.expiry_date and battery.expiry_date < date.today():
        return "expired"
    if not state:
        return "unassigned"
    if state.get("installed"):
        return "installed"
    return "stock"


def stats(db: Session):
    counts = {"total": 0, "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "unassigned": 0}
    batteries, states = current_states(db)
    counts["total"] = len(batteries)
    for battery in batteries:
        state = states.get(battery.id)
        value = status(battery, state, db=db)
        counts[value] = counts.get(value, 0) + 1
    return counts
