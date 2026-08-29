from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment_types.models import EquipmentModel, EquipmentType


def list_equipment(
    db: Session,
    skip: int = 0,
    limit: int = 500,
    operational_status: Optional[str] = None,
    technical_condition: Optional[str] = None,
    equipment_type_id: Optional[int] = None,
) -> list[Equipment]:
    query = db.query(Equipment).options(
        joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)
    )
    if operational_status:
        query = query.filter(Equipment.operational_status == operational_status)
    if technical_condition:
        query = query.filter(Equipment.technical_condition == technical_condition)
    if equipment_type_id:
        query = query.filter(Equipment.equipment_type_id == equipment_type_id)
    return query.order_by(Equipment.id.desc()).offset(skip).limit(limit).all()


def get_equipment(db: Session, equipment_id: int) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.id == equipment_id).first()


def get_by_asset_code(db: Session, asset_code: str) -> Optional[Equipment]:
    return db.query(Equipment).filter(Equipment.asset_code == asset_code).first()


def generate_asset_code(db: Session, registration_number: Optional[str] = None) -> str:
    if registration_number:
        return f"EQ-{registration_number}"
    count = db.query(Equipment).filter(Equipment.registration_number.is_(None)).count()
    next_number = count + 1
    code = f"EQ-TMP-{next_number}"
    while get_by_asset_code(db, code):
        next_number += 1
        code = f"EQ-TMP-{next_number}"
    return code


def create_equipment(
    db: Session, data: EquipmentCreate, user_id: Optional[int] = None
) -> Equipment:
    asset_code = generate_asset_code(db, data.registration_number)
    values = data.model_dump()
    model_id = values.get("equipment_model_id")
    if model_id is not None:
        model = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        if model is None:
            raise ValueError("طراز العتاد المحدد غير موجود")
        if model.equipment_type_id != values["equipment_type_id"]:
            raise ValueError("الطراز المحدد لا ينتمي إلى نوع العتاد المختار")

    equipment = Equipment(
        **values, asset_code=asset_code, created_by_id=user_id, updated_by_id=user_id
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def update_equipment(
    db: Session, equipment: Equipment, data: EquipmentUpdate, user_id: Optional[int] = None
) -> Equipment:
    values = data.model_dump(exclude_unset=True)

    if "registration_number" in values:
        values["registration_number"] = (values["registration_number"] or "").strip() or None
        if values["registration_number"] is not None:
            duplicate = (
                db.query(Equipment)
                .filter(
                    Equipment.registration_number == values["registration_number"],
                    Equipment.id != equipment.id,
                )
                .first()
            )
            if duplicate:
                raise ValueError("رقم التسجيل مستخدم بالفعل لعتاد آخر")

    if "vin" in values:
        values["vin"] = (values["vin"] or "").strip() or None
        if values["vin"] is not None:
            duplicate = (
                db.query(Equipment)
                .filter(Equipment.vin == values["vin"], Equipment.id != equipment.id)
                .first()
            )
            if duplicate:
                raise ValueError("رقم الهيكل مستخدم بالفعل لعتاد آخر")

    type_id = values.get("equipment_type_id", equipment.equipment_type_id)
    model_id = values.get("equipment_model_id", equipment.equipment_model_id)

    if db.query(EquipmentType.id).filter(EquipmentType.id == type_id).first() is None:
        raise ValueError("نوع العتاد المحدد غير موجود")

    if model_id is not None:
        model = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        if model is None:
            raise ValueError("طراز العتاد المحدد غير موجود")
        if model.equipment_type_id != type_id:
            raise ValueError("الطراز المحدد لا ينتمي إلى نوع العتاد المختار")

    if "notes" in values:
        values["notes"] = (values["notes"] or "").strip()[:500] or None

    for field, value in values.items():
        setattr(equipment, field, value)
    equipment.updated_by_id = user_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("تعذر حفظ التعديل: توجد قيمة فريدة مستخدمة مسبقًا") from exc
    db.refresh(equipment)
    return equipment


def delete_equipment(db: Session, equipment: Equipment) -> None:
    db.delete(equipment)
    db.commit()


def count_by_operational_status(db: Session) -> dict[str, int]:
    from sqlalchemy import func

    rows = (
        db.query(Equipment.operational_status, func.count(Equipment.id))
        .group_by(Equipment.operational_status)
        .all()
    )
    return {status: count for status, count in rows}


def count_broken(db: Session) -> int:
    return db.query(Equipment).filter(Equipment.technical_condition == "broken").count()


def update_technical_condition(db: Session, equipment_id: int, condition: str) -> Optional[Equipment]:
    """يُستدعى من وحدات أخرى (مثل maintenance) لتحديث الحالة الفنية آليًا."""
    equipment = get_equipment(db, equipment_id)
    if not equipment:
        return None
    equipment.technical_condition = condition
    db.commit()
    db.refresh(equipment)
    return equipment


def update_operational_status(db: Session, equipment_id: int, status: str) -> Optional[Equipment]:
    """يُستدعى من وحدات أخرى (مثل maintenance) لتحديث الوضعية آليًا."""
    equipment = get_equipment(db, equipment_id)
    if not equipment:
        return None
    equipment.operational_status = status
    db.commit()
    db.refresh(equipment)
    return equipment


def update_meters(db: Session, equipment_id: int, odometer=None, hours=None) -> Optional[Equipment]:
    """يُستدعى من وحدات أخرى (مثل maintenance) لتحديث قراءة العداد الحالية آليًا."""
    equipment = get_equipment(db, equipment_id)
    if not equipment:
        return None
    if odometer is not None:
        equipment.current_odometer = odometer
    if hours is not None:
        equipment.current_hours = hours
    db.commit()
    db.refresh(equipment)
    return equipment
