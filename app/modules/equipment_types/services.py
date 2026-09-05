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


def create_demo_classification(db: Session) -> None:
    """Create the optional example only when its names are not colliding with unrelated user data."""
    category_name = "مثال: مركبات"
    type_name = "مثال: مركبات خفيفة"
    brand_name = "مثال: Toyota"
    model_name = "مثال: Land Cruiser"

    category = db.query(EquipmentCategory).filter(EquipmentCategory.name == category_name).first()
    if category is None:
        category = EquipmentCategory(
            name=category_name,
            code=f"demo-vehicles-{db.query(EquipmentCategory).count() + 1}",
            is_system=False,
        )
        db.add(category)
        db.flush()

    brand = db.query(EquipmentBrand).filter(EquipmentBrand.name == brand_name).first()
    if brand is None:
        brand = EquipmentBrand(name=brand_name, is_active=True)
        db.add(brand)
        db.flush()

    equipment_type = db.query(EquipmentType).filter(EquipmentType.name == type_name).first()
    if equipment_type is None:
        equipment_type = EquipmentType(
            name=type_name,
            measurement_unit="km",
            theoretical_quantity=1,
            category_id=category.id,
        )
        db.add(equipment_type)
        db.flush()
    elif equipment_type.category_id != category.id:
        db.rollback()
        return
    elif equipment_type.theoretical_quantity == 0:
        equipment_type.theoretical_quantity = 1

    model = (
        db.query(EquipmentModel)
        .filter(
            EquipmentModel.equipment_type_id == equipment_type.id,
            EquipmentModel.name == model_name,
        )
        .first()
    )
    if model is None:
        db.add(
            EquipmentModel(
                name=model_name,
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
            )
        )
    elif model.brand_id != brand.id:
        db.rollback()
        return

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
    if get_category(db, data.category_id) is None:
        raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    if data.theoretical_quantity < 0:
        raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
    obj = EquipmentType(
        name=name,
        measurement_unit=data.measurement_unit,
        theoretical_quantity=data.theoretical_quantity,
        category_id=data.category_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def set_type_category(db: Session, obj: EquipmentType, category_id: int) -> EquipmentType:
    if get_category(db, category_id) is None:
        raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    obj.category_id = category_id
    db.commit()
    db.refresh(obj)
    return obj


def set_type_theoretical_quantity(db: Session, obj: EquipmentType, quantity: int) -> EquipmentType:
    if quantity < 0:
        raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
    obj.theoretical_quantity = quantity
    db.commit()
    db.refresh(obj)
    return obj


def delete_type(db: Session, obj: EquipmentType) -> None:
    db.delete(obj)
    db.commit()


def list_models(db: Session, type_id: Optional[int] = None) -> list[EquipmentModel]:
    query = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.brand),
        joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category),
    )
    if type_id:
        query = query.filter(EquipmentModel.equipment_type_id == type_id)
    return query.order_by(EquipmentModel.name).all()


def get_model(db: Session, model_id: int) -> Optional[EquipmentModel]:
    return (
        db.query(EquipmentModel)
        .options(joinedload(EquipmentModel.brand), joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category))
        .filter(EquipmentModel.id == model_id)
        .first()
    )


def create_model(db: Session, data: EquipmentModelCreate) -> EquipmentModel:
    equipment_type = get_type(db, data.equipment_type_id)
    if equipment_type is None:
        raise ValueError("نوع العتاد المحدد غير موجود")
    if equipment_type.category_id is None:
        raise ValueError("لا يمكن إضافة طراز قبل ربط النوع بفئة")
    if get_brand(db, data.brand_id) is None:
        raise ValueError("العلامة التجارية مطلوبة ويجب أن تكون موجودة")
    name = data.name.strip()
    if not name:
        raise ValueError("اسم الطراز مطلوب")
    query = db.query(EquipmentModel).filter(
        EquipmentModel.equipment_type_id == data.equipment_type_id,
        EquipmentModel.name == name,
        EquipmentModel.brand_id == data.brand_id,
    )
    if query.first():
        raise ValueError("الطراز موجود مسبقًا لهذا النوع والعلامة")
    obj = EquipmentModel(name=name, equipment_type_id=data.equipment_type_id, brand_id=data.brand_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def set_model_brand(db: Session, obj: EquipmentModel, brand_id: int) -> EquipmentModel:
    if get_brand(db, brand_id) is None:
        raise ValueError("العلامة التجارية مطلوبة ويجب أن تكون موجودة")
    duplicate = (
        db.query(EquipmentModel)
        .filter(
            EquipmentModel.id != obj.id,
            EquipmentModel.equipment_type_id == obj.equipment_type_id,
            EquipmentModel.brand_id == brand_id,
            EquipmentModel.name == obj.name,
        )
        .first()
    )
    if duplicate:
        raise ValueError("يوجد طراز بالاسم نفسه لهذا النوع والعلامة")
    obj.brand_id = brand_id
    db.commit()
    db.refresh(obj)
    return obj


def delete_model(db: Session, obj: EquipmentModel) -> None:
    db.delete(obj)
    db.commit()
