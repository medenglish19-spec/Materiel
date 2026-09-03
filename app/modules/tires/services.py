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
    if reason in {"تالف", "تلف", "damaged"}:
        return "damaged"
    if reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
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
            state = {"installed": False, "equipment_id": None, "position_id": None, "movement": movement}
        elif movement.movement_type in {"install", "move"}:
            state = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id, "movement": movement}
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
    if position.equipment_model_id != equipment.equipment_model_id:
        raise ValueError("موضع الإطار لا ينتمي إلى طراز العتاد المحدد")
    sizes = {s.size.strip().lower() for s in db.query(TireModelSize).filter(TireModelSize.equipment_model_id == equipment.equipment_model_id).all()}
    if not sizes:
        raise ValueError("لم تُعرّف مقاسات إطارات معتمدة لهذا الطراز")
    if not tire.size or tire.size.strip().lower() not in sizes:
        raise ValueError("مقاس الإطار غير معتمد لهذا الطراز")
    return equipment, position


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
            values.append((reading.reading_date.date(), Decimal(str(value))))
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
    """Ensure tire movement meter values never go backwards while the tire stays on one equipment."""
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
    if db.query(TireDisposal).filter(TireDisposal.tire_id == tire.id).first():
        raise ValueError("الإطار أُخرج نهائيًا من المخزون ولا يمكن تسجيل حركة جديدة له")
    existing = db.query(TireMovement).filter(TireMovement.tire_id == tire.id).order_by(TireMovement.movement_date.asc(), TireMovement.id.asc()).all()
    synthetic_id = max((m.id for m in existing), default=0) + 1
    candidate = TireMovement(id=synthetic_id, tire_id=tire.id, movement_date=movement_date, movement_type=movement_type, equipment_id=equipment_id, position_id=position_id, meter_value=meter_value)
    timeline = sorted(existing + [candidate], key=lambda m: (m.movement_date, m.id))
    _validate_tire_meter_history(timeline)
    state = {"installed": False, "equipment_id": None, "position_id": None}
    for movement in timeline:
        if movement.movement_type == "install":
            if state["installed"]:
                raise ValueError("التسلسل التاريخي غير صالح: الإطار مركب بالفعل قبل عملية التركيب")
            if not movement.equipment_id or not movement.position_id:
                raise ValueError("العتاد وموضع الإطار مطلوبان عند التركيب")
            equipment, _ = _validate_model_position(db, movement.equipment_id, movement.position_id, tire)
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            if _position_occupied_at(db, equipment.id, movement.position_id, movement.movement_date, tire.id, movement if movement is candidate else None):
                raise ValueError("موضع الإطار مشغول بإطار آخر في التاريخ المحدد")
            state = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id}
        elif movement.movement_type == "move":
            if not state["installed"]:
                raise ValueError("لا يمكن نقل إطار غير مركب في التاريخ المحدد")
            if not movement.equipment_id or not movement.position_id:
                raise ValueError("العتاد وموضع الإطار مطلوبان عند النقل")
            equipment, _ = _validate_model_position(db, movement.equipment_id, movement.position_id, tire)
            _validate_equipment_meter(db, equipment.id, movement.movement_date, movement.meter_value)
            if _position_occupied_at(db, equipment.id, movement.position_id, movement.movement_date, tire.id, movement if movement is candidate else None):
                raise ValueError("موضع الإطار الهدف مشغول بإطار آخر في التاريخ المحدد")
            state = {"installed": True, "equipment_id": movement.equipment_id, "position_id": movement.position_id}
        else:
            if not state["installed"]:
                raise ValueError("لا يمكن فك إطار غير مركب في التاريخ المحدد")
            state = {"installed": False, "equipment_id": None, "position_id": None}


def add_tire(db: Session, data: dict):
    data = dict(data)
    if data.get("expiry_date") is None:
        base = data.get("manufacture_date") or data.get("receipt_date")
        if base:
            data["expiry_date"] = _add_years(base, get_validity_years(db))
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


def tire_status(tire: Tire, state):
    if state and state.get("disposition") == "disposed":
        return "disposed"
    if state and state.get("disposition") == "damaged":
        return "damaged"
    if tire.expiry_date and tire.expiry_date < date.today():
        return "expired"
    if state and state.get("installed"):
        return "installed"
    if state:
        return "stock"
    return "unassigned"


def dashboard_stats(db: Session):
    tires = list_tires(db)
    counts = {"total": len(tires), "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "disposed": 0, "unassigned": 0}
    for tire in tires:
        status = tire_status(tire, current_state(db, tire.id))
        counts[status] = counts.get(status, 0) + 1
    return counts


def inventory(db: Session):
    result = []
    for tire in list_tires(db):
        state = current_state(db, tire.id)
        if state and state.get("disposition") == "disposed":
            continue
        if not state or not state["installed"]:
            result.append({"tire": tire, "state": state, "status": tire_status(tire, state)})
    return result


def installed_for_equipment(db: Session, equipment_id: int):
    rows = []
    for tire in list_tires(db):
        state = current_state(db, tire.id)
        if state and state["installed"] and state["equipment"] and state["equipment"].id == equipment_id:
            rows.append({"tire": tire, "state": state})
    return sorted(rows, key=lambda x: x["state"]["position"].sort_order if x["state"]["position"] else 9999)


def equipment_position_view(db: Session, equipment_id: int):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        return []
    configured = list_positions(db, equipment.equipment_model_id)
    mounted = {item["state"]["position"].id: item for item in installed_for_equipment(db, equipment_id) if item["state"]["position"]}
    result = [{"position": p, "item": mounted.get(p.id)} for p in configured]
    configured_ids = {p.id for p in configured}
    for item in mounted.values():
        if item["state"]["position"].id not in configured_ids:
            result.append({"position": item["state"]["position"], "item": item})
    return sorted(result, key=lambda x: (x["position"].axle_number or 9999, x["position"].sort_order, x["position"].id))


def movement_history(db: Session, tire_id: int):
    return _history(db, tire_id)


def model_configuration(db: Session, model_id: int):
    model = db.query(EquipmentModel).options(joinedload(EquipmentModel.brand), joinedload(EquipmentModel.equipment_type)).filter(EquipmentModel.id == model_id).first()
    if not model:
        return None
    positions = list_positions(db, model_id)
    sizes = db.query(TireModelSize).filter(TireModelSize.equipment_model_id == model_id).order_by(TireModelSize.size).all()
    return {"model": model, "positions": positions, "sizes": sizes, "axles": sorted({p.axle_number for p in positions if p.axle_number is not None})}
