from sqlalchemy.orm import Session

from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentType,
)


DEMO_CATEGORY_NAME = "مثال: مركبات"
DEMO_TYPE_NAME = "مثال: مركبات خفيفة"
DEMO_BRAND_NAME = "مثال: Toyota"
DEMO_MODEL_NAME = "مثال: Land Cruiser"


def delete_demo_classification(db: Session) -> None:
    """Remove only the complete built-in example, while preserving real user data."""
    category = db.query(EquipmentCategory).filter(EquipmentCategory.name == DEMO_CATEGORY_NAME).first()
    brand = db.query(EquipmentBrand).filter(EquipmentBrand.name == DEMO_BRAND_NAME).first()
    equipment_type = None
    if category is not None:
        equipment_type = (
            db.query(EquipmentType)
            .filter(EquipmentType.name == DEMO_TYPE_NAME, EquipmentType.category_id == category.id)
            .first()
        )
    if category is None or brand is None or equipment_type is None:
        return
    model = (
        db.query(EquipmentModel)
        .filter(EquipmentModel.equipment_type_id == equipment_type.id, EquipmentModel.name == DEMO_MODEL_NAME, EquipmentModel.brand_id == brand.id)
        .first()
    )
    try:
        if model is not None:
            if db.query(Equipment).filter(Equipment.equipment_model_id == model.id).first():
                raise ValueError("لا يمكن حذف المثال لأن هناك عتادًا فعليًا مرتبطًا بطرازه.")
            db.delete(model)
            db.flush()
        if db.query(EquipmentModel).filter(EquipmentModel.equipment_type_id == equipment_type.id).first() is None:
            db.delete(equipment_type)
            db.flush()
        if db.query(EquipmentType).filter(EquipmentType.category_id == category.id).first() is None:
            db.delete(category)
            db.flush()
        if db.query(EquipmentModel).filter(EquipmentModel.brand_id == brand.id).first() is None:
            db.delete(brand)
        db.commit()
    except Exception:
        db.rollback()
        raise
