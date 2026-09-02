from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.tires.models import Tire, TireMovement, TirePosition

MOVEMENT_TYPES = {"install", "move", "remove"}


def list_tires(db: Session):
    return db.query(Tire).order_by(Tire.serial_number).all()


def list_positions(db: Session):
    return db.query(TirePosition).order_by(TirePosition.sort_order, TirePosition.id).all()


def get_tire(db: Session, tire_id: int):
    return db.query(Tire).options(joinedload(Tire.movements)).filter(Tire.id == tire_id).first()


def _history(db: Session, tire_id: int):
    return (
        db.query(TireMovement)
        .filter(TireMovement.tire_id == tire_id)
        .order_by(TireMovement.movement_date.desc(), TireMovement.id.desc())
        .all()
    )


def current_state(db: Session, tire_id: int):
    movement = (
        db.query(TireMovement)
        .filter(TireMovement.tire_id == tire_id)
        .order_by(TireMovement.movement_date.desc(), TireMovement.id.desc())
        .first()
    )
    if not movement:
        return None
    if movement.movement_type == "remove":
        disposition = "stock"
        reason = (movement.reason or "").strip().lower()
        if reason in {"تالف", "damaged", "تلف"}:
            disposition = "damaged"
        elif reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
            disposition = "expired"
        return {"movement": movement, "installed": False, "equipment": None, "position": None, "disposition": disposition}
    return {
        "movement": movement,
        "installed": movement.equipment_id is not None,
        "equipment": movement.equipment,
        "position": movement.position,
        "disposition": "installed",
    }


def _equipment_position_occupied(db: Session, equipment_id: int, position_id: int, exclude_tire_id: int | None = None):
    q = db.query(TireMovement.tire_id).join(
        Tire,
        Tire.id == TireMovement.tire_id,
    )
    rows = q.filter(TireMovement.equipment_id == equipment_id, TireMovement.position_id == position_id).all()
    for (tire_id,) in rows:
        if exclude_tire_id and tire_id == exclude_tire_id:
            continue
        state = current_state(db, tire_id)
        if state and state["installed"] and state["equipment"] and state["position"]:
            if state["equipment"].id == equipment_id and state["position"].id == position_id:
                return tire_id
    return None


def validate_movement(db: Session, tire: Tire, movement_type: str, movement_date: date,
                      equipment_id: int | None, position_id: int | None,
                      meter_value: Decimal | None):
    if movement_type not in MOVEMENT_TYPES:
        raise ValueError("نوع حركة الإطار غير صالح")
    if movement_date > date.today():
        raise ValueError("لا يمكن تسجيل حركة بتاريخ مستقبلي")

    state = current_state(db, tire.id)
    installed = bool(state and state["installed"])

    if movement_type == "install" and installed:
        raise ValueError("الإطار مركب بالفعل؛ استخدم نقلًا أو فكًا")
    if movement_type == "move" and not installed:
        raise ValueError("لا يمكن نقل إطار غير مركب")
    if movement_type == "remove" and not installed:
        raise ValueError("لا يمكن فك إطار غير مركب")

    if movement_type in {"install", "move"}:
        if not equipment_id or not position_id:
            raise ValueError("العتاد وموضع الإطار مطلوبان عند التركيب أو النقل")
        equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        position = db.query(TirePosition).filter(TirePosition.id == position_id).first()
        if not equipment or not position:
            raise ValueError("العتاد أو موضع الإطار غير موجود")
        occupied = _equipment_position_occupied(db, equipment_id, position_id, tire.id)
        if occupied:
            raise ValueError("موضع الإطار مشغول بإطار آخر")

    if movement_type == "remove":
        equipment_id = None
        position_id = None

    last = (
        db.query(TireMovement)
        .filter(TireMovement.tire_id == tire.id)
        .order_by(TireMovement.movement_date.desc(), TireMovement.id.desc())
        .first()
    )
    if last and movement_date < last.movement_date:
        raise ValueError("تاريخ الحركة لا يمكن أن يسبق آخر حركة للإطار")

    if meter_value is not None and last and last.meter_value is not None and meter_value < last.meter_value:
        raise ValueError("قراءة العداد لا يمكن أن تقل عن القراءة السابقة للإطار")

    if movement_type in {"install", "move"} and equipment_id:
        equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if meter_value is not None and equipment and equipment.current_odometer is not None and meter_value > equipment.current_odometer:
            raise ValueError("قراءة العداد أعلى من العداد الحالي للعتاد")


def add_tire(db: Session, data: dict):
    data = dict(data)
    if data.get("expiry_date") is None:
        base = data.get("manufacture_date") or data.get("receipt_date")
        if base:
            try:
                from dateutil.relativedelta import relativedelta
                data["expiry_date"] = base + relativedelta(years=3)
            except Exception:
                data["expiry_date"] = date(base.year + 3, base.month, base.day)
    tire = Tire(**data)
    db.add(tire)
    db.commit()
    db.refresh(tire)
    return tire


def add_position(db: Session, data: dict):
    position = TirePosition(**data)
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def add_movement(db: Session, tire_id: int, data: dict):
    tire = db.query(Tire).filter(Tire.id == tire_id).first()
    if not tire:
        raise ValueError("الإطار غير موجود")
    validate_movement(db, tire, data["movement_type"], data["movement_date"], data.get("equipment_id"), data.get("position_id"), data.get("meter_value"))
    movement = TireMovement(tire_id=tire_id, **data)
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def tire_status(tire: Tire, state):
    if state and state.get("disposition") in {"damaged", "expired"}:
        return state["disposition"]
    if tire.expiry_date and tire.expiry_date < date.today():
        return "expired"
    if state and state["installed"]:
        return "installed"
    if state:
        return "stock"
    return "unassigned"


def dashboard_stats(db: Session):
    tires = list_tires(db)
    counts = {"total": len(tires), "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "unassigned": 0}
    for tire in tires:
        state = current_state(db, tire.id)
        status = tire_status(tire, state)
        counts[status] = counts.get(status, 0) + 1
    return counts


def inventory(db: Session):
    result = []
    for tire in list_tires(db):
        state = current_state(db, tire.id)
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


def movement_history(db: Session, tire_id: int):
    return _history(db, tire_id)
