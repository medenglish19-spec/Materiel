import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel
from app.modules.meter_readings.models import MeterReading
from app.modules.tires.models import Tire, TireDisposal, TireModelSize, TireMovement, TirePosition, TireSystemSetting

MOVEMENT_TYPES = {"install", "move", "remove"}
SIDES = {"left", "right"}
POSITION_TYPES = {"single", "inner", "outer"}
DAMAGED_REASONS = {"تالف", "damaged", "تلف"}
EXPIRED_REASONS = {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}


def _add_years(value: date, years: int) -> date:
    day = min(value.day, calendar.monthrange(value.year + years, value.month)[1])
    return date(value.year + years, value.month, day)


def list_tires(db: Session):
    return db.query(Tire).order_by(Tire.serial_number).all()


def list_positions(db: Session, equipment_model_id: int | None = None):
    query = db.query(TirePosition)
    if equipment_model_id is not None:
        query = query.filter(TirePosition.equipment_model_id == equipment_model_id)
    return query.order_by(TirePosition.axle_number, TirePosition.sort_order, TirePosition.id).all()


def get_tire(db: Session, tire_id: int):
    return db.query(Tire).options(joinedload(Tire.movements), joinedload(Tire.disposal)).filter(Tire.id == tire_id).first()


def _history(db: Session, tire_id: int):
    return db.query(TireMovement).filter(TireMovement.tire_id == tire_id).order_by(TireMovement.movement_date.desc(), TireMovement.id.desc()).all()


def get_validity_years(db: Session) -> int:
    setting = db.query(TireSystemSetting).filter(TireSystemSetting.id == 1).first()
    if setting is None:
        setting = TireSystemSetting(id=1, validity_years=3)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting.validity_years


def set_validity_years(db: Session, years: int):
    if years < 1 or years > 100:
        raise ValueError("مدة صلاحية الإطارات يجب أن تكون بين سنة واحدة و100 سنة")
    setting = db.query(TireSystemSetting).filter(TireSystemSetting.id == 1).first()
    if setting is None:
        setting = TireSystemSetting(id=1, validity_years=years)
        db.add(setting)
    else:
        setting.validity_years = years
    for tire in db.query(Tire).all():
        base = tire.manufacture_date or tire.receipt_date
        if base:
            tire.expiry_date = _add_years(base, years)
    db.commit()
    db.refresh(setting)
    return setting


def _remove_disposition(movement: TireMovement) -> str:
    reason = (movement.reason or "").strip().lower()
    if reason in DAMAGED_REASONS:
        return "damaged"
    if reason in EXPIRED_REASONS:
        return "expired"
    return "stock"


def current_state(db: Session, tire_id: int):
    movements = db.query(TireMovement).filter(TireMovement.tire_id == tire_id).order_by(TireMovement.movement_date.asc(), TireMovement.id.asc()).all()
    state = None
    for movement in movements:
        if movement.movement_type == "remove":
            state = {"movement": movement, "installed": False, "equipment": None, "position": None, "disposition": _remove_disposition(movement)}
        else:
            state = {"movement": movement, "installed": True, "equipment": movement.equipment, "position": movement.position, "disposition": "installed"}
    disposal = db.query(TireDisposal).filter(TireDisposal.tire_id == tire_id).first()
    if disposal and (state is None or disposal.disposal_date >= state["movement"].movement_date):
        return {"movement": state["movement"] if state else None, "installed": False, "equipment": None, "position": None, "disposition": "disposed", "disposal": disposal}
    return state


def _state_from_history(movements):
    state = {"installed": False, "equipment_id": None, "position_id": None, "movement": None}
    for movement in sorted(movements, key=lambda m: (m.movement_date, m.id)):
        if movement.movement_type == "remove":
            state = {"installed": False, "equipment_id": None, "position_id": None, "movement": movement, "disposition": _remove_disposition(movement)}
        elif movement.movement_type in {"install", "move"}:
            state = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id, "movement": movement, "disposition": "installed"}
    return state


def _tire_state_at(db: Session, tire_id: int, when: date, extra=None):
    movements = db.query(TireMovement).filter(TireMovement.tire_id == tire_id, TireMovement.movement_date <= when).all()
    if extra is not None:
        movements.append(extra)
    return _state_from_history(movements)


def _validate_model_position(db: Session, equipment_id: int, position_id: int, tire: Tire):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    position = db.query(TirePosition).filter(TirePosition.id == position_id).first()
    if not equipment or not position:
        raise ValueError("العتاد أو موضع الإطار غير موجود")
    if position.equipment_model_id is not None and position.equipment_model_id != equipment.equipment_model_id:
        raise ValueError("موضع الإطار لا ينتمي إلى طراز العتاد المحدد")
    model = equipment.equipment_model
    if model is None:
        raise ValueError("لا يمكن تركيب الإطار على عتاد لا يرتبط بطراز")
    sizes = {s.size.strip().lower() for s in db.query(TireModelSize).filter(TireModelSize.equipment_model_id == equipment.equipment_model_id).all() if s.size and s.size.strip()}
    model_size = (model.tire_size or "").strip().lower() if getattr(model, "tire_size", None) else ""
    tire_size = (tire.size or "").strip().lower() if tire.size else ""
    if sizes:
        if not tire_size or tire_size not in sizes:
            raise ValueError("مقاس الإطار غير معتمد لهذا الطراز")
    elif model_size:
        if not tire_size or tire_size != model_size:
            raise ValueError("مقاس الإطار غير مطابق للمقاس المعتمد لهذا الطراز")
    else:
        raise ValueError("لا يمكن تركيب الإطار: لم يتم تحديد أي مقاس إطار معتمد لهذا الطراز في Master Data. يرجى إضافة المقاس المعتمد للطراز قبل إجراء عملية التركيب.")
    return equipment, position


def _installed_tire_count(db: Session, equipment_id: int, exclude_tire_id: int | None = None, when: date | None = None):
    count = 0
    tires = db.query(Tire).all()
    for tire in tires:
        if exclude_tire_id is not None and tire.id == exclude_tire_id:
            continue
        state = _tire_state_at(db, tire.id, when) if when is not None else current_state(db, tire.id)
        if state and state.get("installed") and state.get("equipment_id") == equipment_id:
            count += 1
    return count


def _validate_model_capacity(db: Session, equipment_id: int, tire_id: int, movement_type: str, when: date | None = None):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment or equipment.equipment_model is None:
        raise ValueError("لا يمكن تركيب الإطار على عتاد لا يرتبط بطراز")
    model = equipment.equipment_model
    required = int(model.tire_positions_required or 0)
    if required <= 0 or movement_type not in {"install", "move"}:
        return
    if when is None:
        installed = _installed_tire_count(db, equipment_id, exclude_tire_id=tire_id)
    else:
        installed = _installed_tire_count(db, equipment_id, exclude_tire_id=tire_id, when=when)
    if installed >= required:
        raise ValueError(f"تم بلوغ العدد المحدد للإطارات لهذا الطراز ({required}). يجب فك إطار أولًا أو اختيار موضع/عتاد آخر.")


def _position_occupied_at(db: Session, equipment_id: int, position_id: int, when: date, exclude_tire_id: int | None = None, extra=None):
    tire_ids = [row[0] for row in db.query(TireMovement.tire_id).filter(TireMovement.equipment_id == equipment_id, TireMovement.position_id == position_id).distinct().all()]
    for tire_id in tire_ids:
        if exclude_tire_id and tire_id == exclude_tire_id:
            continue
        state = _tire_state_at(db, tire_id, when)
        if state["installed"] and state["equipment_id"] == equipment_id and state["position_id"] == position_id:
            return tire_id
    if extra is not None and extra.equipment_id == equipment_id and extra.position_id == position_id and extra.tire_id != exclude_tire_id:
        return extra.tire_id
    return None


def _validate_equipment_meter(db: Session, equipment_id: int, movement_date: date, meter_value: Decimal | None):
    if meter_value is None:
        return
    readings = db.query(MeterReading).filter(MeterReading.equipment_id == equipment_id).order_by(MeterReading.reading_date.asc(), MeterReading.id.asc()).all()
    values = []
    for reading in readings:
        value = reading.odometer if reading.odometer is not None else reading.hours
        if value is not None:
            reading_date = reading.reading_date.date() if hasattr(reading.reading_date, "date") else reading.reading_date
            values.append((reading_date, Decimal(str(value))))
    before = [value for d, value in values if d <= movement_date]
    after = [value for d, value in values if d >= movement_date]
    if before and meter_value < before[-1]:
        raise ValueError("قراءة العداد أقل من آخر قراءة معروفة للعتاد قبل هذا التاريخ")
    if after and meter_value > after[0]:
        raise ValueError("قراءة العداد أكبر من أول قراءة معروفة للعتاد بعد هذا التاريخ")
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if equipment and equipment.current_odometer is not None and meter_value > equipment.current_odometer:
        raise ValueError("قراءة العداد أعلى من العداد الحالي للعتاد")


def _validate_tire_meter_history(movements):
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
            raise ValueError("قراءات عداد حركات الإطار غير متوافقة مع التسلسل الزمني للعتاد")
        previous_equipment_id = movement.equipment_id
        previous = value


def validate_movement(db: Session, tire: Tire, movement_type: str, movement_date: date, equipment_id: int | None, position_id: int | None, meter_value: Decimal | None):
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("نوع حركة الإطار غير صالح")
    if movement_date > date.today():
        raise ValueError("لا يمكن تسجيل حركة بتاريخ مستقبلي")
    if db is None:
        if movement_type in {"install", "move"} and (not equipment_id or not position_id):
            raise ValueError("العتاد وموضع الإطار مطلوبان عند التركيب أو النقل")
        return
    disposal = db.query(TireDisposal).filter(TireDisposal.tire_id == tire.id).first()
    if disposal and disposal.disposal_date <= movement_date:
        raise ValueError("الإطار أُخرج نهائيًا من المخزون ولا يمكن تسجيل حركة بتاريخ الإخراج أو بعده")
    existing = db.query(TireMovement).filter(TireMovement.tire_id == tire.id).order_by(TireMovement.movement_date.asc(), TireMovement.id.asc()).all()
    synthetic_id = max((m.id for m in existing), default=0) + 1
    candidate = TireMovement(id=synthetic_id, tire_id=tire.id, movement_date=movement_date, movement_type=movement_type, equipment_id=equipment_id, position_id=position_id, meter_value=meter_value)
    timeline = sorted(existing + [candidate], key=lambda m: (m.movement_date, m.id))
    _validate_tire_meter_history(timeline)
    initial_state = current_state(db, tire.id) if not existing else None
    state_at = {"installed": False, "equipment_id": None, "position_id": None, "disposition": "stock"}
    if initial_state and not initial_state.get("installed") and initial_state.get("disposition") in {"damaged", "expired"}:
        state_at["disposition"] = initial_state["disposition"]
    for movement in timeline:
        if movement.movement_type == "install":
            if state_at["installed"]:
                raise ValueError("التسلسل التاريخي غير صالح: الإطار مركب بالفعل قبل عملية التركيب")
            if not movement.equipment_id or not movement.position_id:
                raise ValueError("العتاد وموضع الإطار مطلوبان عند التركيب")
            if state_at["disposition"] in {"damaged", "expired"}:
                label = "تالف" if state_at["disposition"] == "damaged" else "منتهي الصلاحية"
                raise ValueError(f"لا يمكن تركيب إطار {label} بعد تسجيل إخراجه بهذه الحالة")
            if tire.expiry_date and movement.movement_date > tire.expiry_date:
                raise ValueError("لا يمكن تركيب إطار منتهي الصلاحية في تاريخ الحركة المحدد")
            equipment, _ = _validate_model_position(db, movement.equipment_id, movement.position_id, tire)
            _validate_model_capacity(db, equipment.id, tire.id, "install", movement.movement_date)
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            if _position_occupied_at(db, equipment.id, movement.position_id, movement.movement_date, tire.id, movement if movement is candidate else None):
                raise ValueError("موضع الإطار مشغول بإطار آخر في التاريخ المحدد")
            state_at = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id, "disposition": "installed"}
        elif movement.movement_type == "move":
            if not state_at["installed"]:
                raise ValueError("لا يمكن نقل إطار غير مركب في التاريخ المحدد")
            if not movement.equipment_id or not movement.position_id:
                raise ValueError("العتاد وموضع الإطار مطلوبان عند النقل")
            if tire.expiry_date and movement.movement_date > tire.expiry_date:
                raise ValueError("لا يمكن نقل إطار منتهي الصلاحية في تاريخ الحركة المحدد")
            equipment, _ = _validate_model_position(db, movement.equipment_id, movement.position_id, tire)
            _validate_model_capacity(db, equipment.id, tire.id, "move", movement.movement_date)
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            if _position_occupied_at(db, equipment.id, movement.position_id, movement.movement_date, tire.id, movement if movement is candidate else None):
                raise ValueError("موضع الإطار الهدف مشغول بإطار آخر في التاريخ المحدد")
            state_at = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id, "disposition": "installed"}
        elif movement.movement_type == "remove":
            if not state_at["installed"]:
                raise ValueError("لا يمكن فك إطار غير مركب في التاريخ المحدد")
            state_at = {"installed": False, "equipment_id": None, "position_id": None, "disposition": _remove_disposition(movement)}


def add_tire(db: Session, data: dict):
    data = dict(data)
    serial_number = (data.get("serial_number") or "").strip()
    if not serial_number:
        raise ValueError("الرقم التسلسلي للإطار مطلوب")
    if db.query(Tire.id).filter(Tire.serial_number == serial_number).first():
        raise ValueError("الرقم التسلسلي للإطار مستخدم مسبقًا")
    data["serial_number"] = serial_number
    manufacture_date = data.get("manufacture_date")
    receipt_date = data.get("receipt_date")
    expiry_date = data.get("expiry_date")
    base = manufacture_date or receipt_date
    if expiry_date is None and base:
        data["expiry_date"] = _add_years(base, get_validity_years(db))
    elif expiry_date and manufacture_date and expiry_date < manufacture_date:
        raise ValueError("تاريخ انتهاء الصلاحية لا يمكن أن يسبق تاريخ التصنيع")
    elif expiry_date and receipt_date and expiry_date < receipt_date:
        raise ValueError("تاريخ انتهاء الصلاحية لا يمكن أن يسبق تاريخ الاستلام")
    tire = Tire(**data)
    db.add(tire)
    db.commit()
    db.refresh(tire)
    return tire


def add_model_size(db: Session, equipment_model_id: int, size: str):
    model = db.query(EquipmentModel).filter(EquipmentModel.id == equipment_model_id).first()
    size = (size or "").strip()
    if not model or not size:
        raise ValueError("الطراز والمقاس مطلوبان")
    if db.query(TireModelSize).filter(TireModelSize.equipment_model_id == equipment_model_id, TireModelSize.size.ilike(size)).first():
        raise ValueError("المقاس مضاف مسبقًا لهذا الطراز")
    obj = TireModelSize(equipment_model_id=equipment_model_id, size=size)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_model_size(db: Session, size_id: int):
    obj = db.query(TireModelSize).filter(TireModelSize.id == size_id).first()
    if not obj:
        return
    for tire in list_tires(db):
        state = current_state(db, tire.id)
        if state and state.get("installed") and state.get("equipment") and state["equipment"].equipment_model_id == obj.equipment_model_id and tire.size and tire.size.strip().lower() == obj.size.strip().lower():
            raise ValueError("لا يمكن حذف مقاس ما زال مستخدمًا على إطار مركب لهذا الطراز")
    db.delete(obj)
    db.commit()


def add_position(db: Session, equipment_model_id: int, axle_number: int, side: str, position_type: str, description: str = ""):
    model = db.query(EquipmentModel).filter(EquipmentModel.id == equipment_model_id).first()
    if not model:
        raise ValueError("الطراز غير موجود")
    if axle_number < 1 or side not in SIDES or position_type not in POSITION_TYPES:
        raise ValueError("بيانات موضع الإطار غير صالحة")
    if db.query(TirePosition).filter(TirePosition.equipment_model_id == equipment_model_id, TirePosition.axle_number == axle_number, TirePosition.side == side, TirePosition.position_type == position_type).first():
        raise ValueError("هذا الموضع موجود مسبقًا لهذا الطراز")
    code = f"M{equipment_model_id}-A{axle_number}-{side}-{position_type}"
    name_side = "يسار" if side == "left" else "يمين"
    name_type = {"single": "مفرد", "inner": "داخلي", "outer": "خارجي"}[position_type]
    obj = TirePosition(equipment_model_id=equipment_model_id, axle_number=axle_number, side=side, position_type=position_type, code=code, name=f"المحور {axle_number} — {name_side} {name_type}", description=description.strip() or None, sort_order=axle_number)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_position(db: Session, position_id: int):
    obj = db.query(TirePosition).filter(TirePosition.id == position_id).first()
    if not obj:
        return
    if db.query(TireMovement).filter(TireMovement.position_id == position_id).first():
        raise ValueError("لا يمكن حذف موضع استُخدم في سجل حركات؛ حافظ على التاريخ")
    db.delete(obj)
    db.commit()


def add_movement(db: Session, tire_id: int, data: dict):
    tire = db.query(Tire).filter(Tire.id == tire_id).first()
    if not tire:
        raise ValueError("الإطار غير موجود")
    validate_movement(db, tire, data["movement_type"], data["movement_date"], data.get("equipment_id"), data.get("position_id"), data.get("meter_value"))
    if data["movement_type"] == "remove":
        data["equipment_id"] = None
        data["position_id"] = None
    movement = TireMovement(tire_id=tire_id, **data)
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def dispose_tire(db: Session, tire_id: int, disposal_date: date, document: str, reason: str, notes: str = ""):
    tire = db.query(Tire).filter(Tire.id == tire_id).first()
    if not tire:
        raise ValueError("الإطار غير موجود")
    if disposal_date > date.today():
        raise ValueError("لا يمكن تسجيل إخراج بتاريخ مستقبلي")
    if db.query(TireDisposal).filter(TireDisposal.tire_id == tire_id).first():
        raise ValueError("الإطار أُخرج من المخزون مسبقًا")
    if db.query(TireMovement).filter(TireMovement.tire_id == tire_id, TireMovement.movement_date > disposal_date).first():
        raise ValueError("تاريخ الإخراج لا يمكن أن يسبق حركة تاريخية لاحقة")
    if _tire_state_at(db, tire_id, disposal_date)["installed"]:
        raise ValueError("يجب أن يكون الإطار خارج العتاد في تاريخ الإخراج")
    document = (document or "").strip()
    reason = (reason or "").strip()
    if not document or not reason:
        raise ValueError("وثيقة الإخراج وسبب الإخراج مطلوبان")
    obj = TireDisposal(tire_id=tire_id, disposal_date=disposal_date, disposal_document=document, reason=reason, notes=notes.strip() or None)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
