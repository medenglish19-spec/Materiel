from datetime import date
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.missions.models import Mission


def active_mission_equipment_ids(db: Session, equipment_ids: list, today: Optional[date] = None) -> set:
    """معرّفات العتاد الذي لديه مهمة جارية اليوم، باستعلام واحد لكل 500 معرّف.

    الغرض: تفادي N+1 عند حساب الوضعية الفعّالة لصفحة كاملة.
    """
    ids = {i for i in equipment_ids if i is not None}
    if not ids:
        return set()
    today = today or date.today()
    ordered = sorted(ids)
    active: set = set()
    for start in range(0, len(ordered), 500):
        rows = (
            db.query(Mission.equipment_id)
            .filter(
                Mission.equipment_id.in_(ordered[start : start + 500]),
                Mission.start_date <= today,
                (Mission.end_date.is_(None) | (Mission.end_date >= today)),
            )
            .distinct()
            .all()
        )
        active.update(row[0] for row in rows)
    return active


def active_repair_workshops(db: Session, equipment_ids: list) -> dict:
    """الحالة التشغيلية الناتجة عن الإصلاحات النشطة، مستقلة عن آخر قراءة عداد."""
    if not equipment_ids:
        return {}
    from app.modules.faults_repairs.models import Fault, Repair

    rows = (
        db.query(Fault.equipment_id, Repair.workshop_type)
        .join(Repair, Repair.fault_id == Fault.id)
        .filter(
            Fault.equipment_id.in_(equipment_ids),
            Repair.status == "in_progress",
        )
        .all()
    )
    result = {}
    for equipment_id, workshop_type in rows:
        # الورشة الخارجية لها أولوية إذا وُجد إصلاحان نشطان لنفس العتاد.
        if workshop_type == "external":
            result[equipment_id] = "in_external_workshop"
        elif equipment_id not in result:
            result[equipment_id] = "in_maintenance"
    return result


def _effective_status(
    equipment: Equipment,
    active_equipment_ids: set,
    active_repairs: dict,
) -> str:
    """قاعدة الوضعية الفعّالة الحالية، مع أولوية الإصلاح النشط."""
    if equipment.technical_condition == "broken":
        return "unavailable"
    repair_status = active_repairs.get(equipment.id)
    if repair_status:
        return repair_status
    if equipment.operational_status in {"in_maintenance", "in_external_workshop", "unavailable"}:
        return equipment.operational_status
    if equipment.id in active_equipment_ids:
        return "in_mission"
    return "available"


def effective_operational_status(db: Session, equipment: Equipment, today: Optional[date] = None) -> str:
    active = active_mission_equipment_ids(db, [equipment.id], today=today)
    repairs = active_repair_workshops(db, [equipment.id])
    return _effective_status(equipment, active, repairs)


def effective_operational_statuses(db: Session, items: list, today: Optional[date] = None) -> dict:
    """الوضعية الفعّالة لكل العتاد، من الحالة الحالية لا من قراءة عداد تاريخية."""
    ids = [item.id for item in items]
    active = active_mission_equipment_ids(db, ids, today=today)
    repairs = active_repair_workshops(db, ids)
    return {item.id: _effective_status(item, active, repairs) for item in items}


def list_equipment(db: Session, skip: int = 0, limit: int = 500, operational_status: Optional[str] = None, technical_condition: Optional[str] = None, equipment_type_id: Optional[int] = None) -> list[Equipment]:
    query = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model))
    if operational_status: query = query.filter(Equipment.operational_status == operational_status)
    if technical_condition: query = query.filter(Equipment.technical_condition == technical_condition)
    if equipment_type_id: query = query.filter(Equipment.equipment_type_id == equipment_type_id)
    return query.order_by(Equipment.id.desc()).offset(skip).limit(limit).all()


def get_equipment(db: Session, equipment_id: int) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.id == equipment_id).first()


def get_by_asset_code(db: Session, asset_code: str) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.asset_code == asset_code).first()


def generate_asset_code(db: Session, registration_number: Optional[str] = None) -> str:
    if registration_number: return f"EQ-{registration_number}"
    count = db.query(Equipment).filter(Equipment.registration_number.is_(None)).count(); next_number = count + 1; code = f"EQ-TMP-{next_number}"
    while get_by_asset_code(db, code): next_number += 1; code = f"EQ-TMP-{next_number}"
    return code


def create_equipment(db: Session, data: EquipmentCreate, user_id: Optional[int] = None) -> Equipment:
    asset_code = generate_asset_code(db, data.registration_number); values = data.model_dump(); type_id = values["equipment_type_id"]; model_id = values.get("equipment_model_id")
    equipment_type = db.query(EquipmentType).filter(EquipmentType.id == type_id).first()
    if equipment_type is None: raise ValueError("نوع العتاد المحدد غير موجود")
    if equipment_type.is_frozen: raise ValueError("نوع العتاد مجمد؛ لا يمكن اعتماد عتاد جديد عليه قبل إعادة اعتماده")
    if model_id is not None:
        model = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        if model is None: raise ValueError("طراز العتاد المحدد غير موجود")
        if model.equipment_type_id != type_id: raise ValueError("الطراز المحدد لا ينتمي إلى نوع العتاد المختار")
        if model.is_frozen: raise ValueError("طراز العتاد مجمد؛ لا يمكن اعتماد عتاد جديد عليه قبل إعادة اعتماده")
    if values.get("technical_condition") == "broken": values["operational_status"] = "unavailable"
    equipment = Equipment(**values, asset_code=asset_code, created_by_id=user_id, updated_by_id=user_id); db.add(equipment); db.commit(); db.refresh(equipment); return equipment


def update_equipment(db: Session, equipment: Equipment, data: EquipmentUpdate, user_id: Optional[int] = None) -> Equipment:
    values = data.model_dump(exclude_unset=True)
    if "registration_number" in values:
        values["registration_number"] = (values["registration_number"] or "").strip() or None
        if values["registration_number"] is not None and db.query(Equipment).filter(Equipment.registration_number == values["registration_number"], Equipment.id != equipment.id).first(): raise ValueError("رقم التسجيل مستخدم بالفعل لعتاد آخر")
    if "vin" in values:
        values["vin"] = (values["vin"] or "").strip() or None
        if values["vin"] is not None and db.query(Equipment).filter(Equipment.vin == values["vin"], Equipment.id != equipment.id).first(): raise ValueError("رقم الهيكل مستخدم بالفعل لعتاد آخر")
    type_id = values.get("equipment_type_id", equipment.equipment_type_id); model_id = values.get("equipment_model_id", equipment.equipment_model_id)
    target_type = db.query(EquipmentType).filter(EquipmentType.id == type_id).first()
    if target_type is None: raise ValueError("نوع العتاد المحدد غير موجود")
    if (type_id != equipment.equipment_type_id or model_id != equipment.equipment_model_id) and target_type.is_frozen: raise ValueError("نوع العتاد مجمد؛ لا يمكن اعتماد نقل العتاد إليه قبل إعادة اعتماده")
    if model_id is not None:
        model = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        if model is None: raise ValueError("طراز العتاد المحدد غير موجود")
        if model.equipment_type_id != type_id: raise ValueError("الطراز المحدد لا ينتمي إلى نوع العتاد المختار")
        if model_id != equipment.equipment_model_id and model.is_frozen: raise ValueError("طراز العتاد مجمد؛ لا يمكن اعتماد نقل العتاد إليه قبل إعادة اعتماده")
    if model_id != equipment.equipment_model_id:
        from app.modules.tires.services import installed_for_equipment
        if installed_for_equipment(db, equipment.id):
            raise ValueError("لا يمكن تغيير طراز العتاد بينما توجد إطارات مركبة عليه؛ يجب فك الإطارات أولًا للحفاظ على التاريخ واتساق بيانات Master Data")
    if values.get("technical_condition", equipment.technical_condition) == "broken": values["operational_status"] = "unavailable"
    if "notes" in values: values["notes"] = (values["notes"] or "").strip()[:500] or None
    for field, value in values.items(): setattr(equipment, field, value)
    equipment.updated_by_id = user_id
    try: db.commit()
    except IntegrityError as exc: db.rollback(); raise ValueError("تعذر حفظ التعديل: توجد قيمة فريدة مستخدمة مسبقًا") from exc
    db.refresh(equipment); return equipment


def delete_equipment(db: Session, equipment: Equipment) -> None: db.delete(equipment); db.commit()


def count_by_operational_status(db: Session) -> dict[str, int]:
    from sqlalchemy import func
    rows = db.query(Equipment.operational_status, func.count(Equipment.id)).group_by(Equipment.operational_status).all(); return {status: count for status, count in rows}


def count_broken(db: Session) -> int: return db.query(Equipment).filter(Equipment.technical_condition == "broken").count()


def update_technical_condition(db: Session, equipment_id: int, condition: str) -> Optional[Equipment]:
    equipment = get_equipment(db, equipment_id)
    if not equipment: return None
    equipment.technical_condition = condition
    if condition == "broken": equipment.operational_status = "unavailable"
    db.commit(); db.refresh(equipment); return equipment


def update_operational_status(db: Session, equipment_id: int, status: str) -> Optional[Equipment]:
    equipment = get_equipment(db, equipment_id)
    if not equipment: return None
    if status == "available" and equipment.technical_condition == "broken": status = "unavailable"
    equipment.operational_status = status; db.commit(); db.refresh(equipment); return equipment


def update_meters(db: Session, equipment_id: int, odometer=None, hours=None) -> Optional[Equipment]:
    equipment = get_equipment(db, equipment_id)
    if not equipment: return None
    if odometer is not None: equipment.current_odometer = odometer
    if hours is not None: equipment.current_hours = hours
    db.commit(); db.refresh(equipment); return equipment
