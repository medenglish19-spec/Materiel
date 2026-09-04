from typing import Optional
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentType,
)
from app.modules.equipment_types.schemas import (
    EquipmentBrandCreate,
    EquipmentCategoryCreate,
    EquipmentModelCreate,
    EquipmentTypeCreate,
)


def list_categories(db: Session) -> list[EquipmentCategory]:
    return db.query(EquipmentCategory).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()


def get_category(db: Session, category_id: int) -> Optional[EquipmentCategory]:
    return db.query(EquipmentCategory).filter(EquipmentCategory.id == category_id).first()


def create_category(db: Session, data: EquipmentCategoryCreate) -> EquipmentCategory:
    name = data.name.strip()
    if not name:
        raise ValueError("اسم الفئة مطلوب")
    if db.query(EquipmentCategory).filter(EquipmentCategory.name == name).first():
        raise ValueError("الفئة موجودة مسبقًا")
    code = (data.code or name).strip().lower().replace(" ", "-")[:30]
    if not code:
        code = f"category-{db.query(EquipmentCategory).count() + 1}"
    if db.query(EquipmentCategory).filter(EquipmentCategory.code == code).first():
        code = f"{code}-{db.query(EquipmentCategory).count() + 1}"[:30]
    obj = EquipmentCategory(name=name, code=code, is_system=False)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_category(db: Session, obj: EquipmentCategory) -> None:
    if obj.is_system:
        raise ValueError("الفئات الأساسية للنظام لا يمكن حذفها")
    db.delete(obj)
    db.commit()


def list_brands(db: Session, active_only: bool = True) -> list[EquipmentBrand]:
    query = db.query(EquipmentBrand)
    if active_only:
        query = query.filter(EquipmentBrand.is_active.is_(True))
    return query.order_by(EquipmentBrand.name).all()


def get_brand(db: Session, brand_id: int) -> Optional[EquipmentBrand]:
    return db.query(EquipmentBrand).filter(EquipmentBrand.id == brand_id).first()


def create_brand(db: Session, data: EquipmentBrandCreate) -> EquipmentBrand:
    name = data.name.strip()
    if not name:
        raise ValueError("اسم العلامة التجارية مطلوب")
    if db.query(EquipmentBrand).filter(EquipmentBrand.name == name).first():
        raise ValueError("العلامة التجارية موجودة مسبقًا")
    obj = EquipmentBrand(name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def list_types(db: Session) -> list[EquipmentType]:
    return (
        db.query(EquipmentType)
        .options(
            joinedload(EquipmentType.models).joinedload(EquipmentModel.brand),
            joinedload(EquipmentType.category),
        )
        .order_by(EquipmentType.name)
        .all()
    )


def get_type(db: Session, type_id: int) -> Optional[EquipmentType]:
    return (
        db.query(EquipmentType)
        .options(joinedload(EquipmentType.category))
        .filter(EquipmentType.id == type_id)
        .first()
    )


def get_type_by_name(db: Session, name: str) -> Optional[EquipmentType]:
    return db.query(EquipmentType).filter(EquipmentType.name == name).first()


def create_type(db: Session, data: EquipmentTypeCreate) -> EquipmentType:
    name = data.name.strip()
    if not name:
        raise ValueError("اسم نوع العتاد مطلوب")
    if get_type_by_name(db, name):
        raise ValueError("نوع العتاد موجود مسبقًا")
    if data.category_id is not None and get_category(db, data.category_id) is None:
        raise ValueError("فئة العتاد المحددة غير موجودة")
    obj = EquipmentType(
        name=name,
        measurement_unit=data.measurement_unit,
        category_id=data.category_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def set_type_category(db: Session, obj: EquipmentType, category_id: Optional[int]) -> EquipmentType:
    if category_id is not None and get_category(db, category_id) is None:
        raise ValueError("فئة العتاد المحددة غير موجودة")
    obj.category_id = category_id
    db.commit()
    db.refresh(obj)
    return obj


def delete_type(db: Session, obj: EquipmentType) -> None:
    db.delete(obj)
    db.commit()


def list_models(db: Session, type_id: Optional[int] = None) -> list[EquipmentModel]:
    query = db.query(EquipmentModel).options(joinedload(EquipmentModel.brand))
    if type_id:
        query = query.filter(EquipmentModel.equipment_type_id == type_id)
    return query.order_by(EquipmentModel.name).all()


def get_model(db: Session, model_id: int) -> Optional[EquipmentModel]:
    return (
        db.query(EquipmentModel)
        .options(joinedload(EquipmentModel.brand))
        .filter(EquipmentModel.id == model_id)
        .first()
    )


def create_model(db: Session, data: EquipmentModelCreate) -> EquipmentModel:
    if get_type(db, data.equipment_type_id) is None:
        raise ValueError("نوع العتاد المحدد غير موجود")
    if data.brand_id is not None and get_brand(db, data.brand_id) is None:
        raise ValueError("العلامة التجارية المحددة غير موجودة")
    name = data.name.strip()
    if not name:
        raise ValueError("اسم الطراز مطلوب")
    query = db.query(EquipmentModel).filter(
        EquipmentModel.equipment_type_id == data.equipment_type_id,
        EquipmentModel.name == name,
    )
    if data.brand_id is None:
        query = query.filter(EquipmentModel.brand_id.is_(None))
    else:
        query = query.filter(EquipmentModel.brand_id == data.brand_id)
    if query.first():
        raise ValueError("الطراز موجود مسبقًا لهذا النوع والعلامة التجارية")
    obj = EquipmentModel(
        name=name,
        equipment_type_id=data.equipment_type_id,
        brand_id=data.brand_id,
        theoretical_quantity=max(0, data.theoretical_quantity),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def set_model_brand(db: Session, obj: EquipmentModel, brand_id: Optional[int]) -> EquipmentModel:
    if brand_id is not None and get_brand(db, brand_id) is None:
        raise ValueError("العلامة التجارية المحددة غير موجودة")
    duplicate = (
        db.query(EquipmentModel)
        .filter(
            EquipmentModel.equipment_type_id == obj.equipment_type_id,
            EquipmentModel.brand_id == brand_id,
            EquipmentModel.name == obj.name,
            EquipmentModel.id != obj.id,
        )
        .first()
    )
    if duplicate:
        raise ValueError("يوجد طراز بنفس الاسم لنوع العتاد والعلامة التجارية المحددين")
    obj.brand_id = brand_id
    db.commit()
    db.refresh(obj)
    return obj


def set_model_theoretical_quantity(db: Session, obj: EquipmentModel, theoretical_quantity: int) -> EquipmentModel:
    if theoretical_quantity < 0:
        raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
    obj.theoretical_quantity = theoretical_quantity
    db.commit()
    db.refresh(obj)
    return obj


def delete_model(db: Session, obj: EquipmentModel) -> None:
    db.delete(obj)
    db.commit()
