from sqlalchemy.orm import Session

from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentType,
)
from app.modules.maintenance.models import MaintenanceRecord, MaintenanceRule


DEMO_CATEGORY_NAME = "مثال: مركبات"
DEMO_TYPE_NAME = "مثال: مركبات خفيفة"
DEMO_BRAND_NAME = "مثال: Toyota"
DEMO_MODEL_NAME = "مثال: Land Cruiser"


def delete_demo_classification(db: Session) -> None:
    """Remove only the built-in example, while preserving any real user data."""
    category = db.query(EquipmentCategory).filter(EquipmentCategory.name == DEMO_CATEGORY_NAME).first()
    equipment_type = db.query(EquipmentType).filter(EquipmentType.name == DEMO_TYPE_NAME).first()
    brand = db.query(EquipmentBrand).filter(EquipmentBrand.name == DEMO_BRAND_NAME).first()

    model = None
    if equipment_type is not None:
        model = (
            db.query(EquipmentModel)
            .filter(
                EquipmentModel.equipment_type_id == equipment_type.id,
                EquipmentModel.name == DEMO_MODEL_NAME,
                EquipmentModel.brand_id == (brand.id if brand is not None else None),
            )
            .first()
        )

    try:
        if model is not None:
            if db.query(Equipment).filter(Equipment.equipment_model_id == model.id).first():
                raise ValueError("لا يمكن حذف المثال لأن هناك عتادًا فعليًا مرتبطًا بطرازه.")

            rules = db.query(MaintenanceRule).filter(MaintenanceRule.equipment_model_id == model.id).all()
            rule_ids = [rule.id for rule in rules]
            if rule_ids and db.query(MaintenanceRecord).filter(MaintenanceRecord.rule_id.in_(rule_ids)).first():
                raise ValueError("لا يمكن حذف المثال لأن له سجلات صيانة محفوظة.")

            db.delete(model)
            db.flush()

        # Never remove a type/category/brand that the user has reused elsewhere.
        if equipment_type is not None and db.query(EquipmentModel).filter(EquipmentModel.equipment_type_id == equipment_type.id).first() is None:
            db.delete(equipment_type)
            db.flush()

        if category is not None and db.query(EquipmentType).filter(EquipmentType.category_id == category.id).first() is None:
            db.delete(category)
            db.flush()

        if brand is not None and db.query(EquipmentModel).filter(EquipmentModel.brand_id == brand.id).first() is None:
            db.delete(brand)

        db.commit()
    except Exception:
        db.rollback()
        raise
