import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
# Import all models that participate in foreign keys before create_all().
# User is referenced by the audit columns on several tables (including tires).
from app.modules.users.models import User  # noqa: F401
from app.modules.equipment_types import services
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentType,
)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def _session():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def test_delete_unused_brand_succeeds():
    db = _session()
    try:
        brand = EquipmentBrand(name="علامة غير مستخدمة", is_active=True)
        db.add(brand)
        db.commit()
        db.refresh(brand)

        services.delete_brand(db, brand)

        assert services.get_brand(db, brand.id) is None
    finally:
        db.close()


def test_delete_brand_used_by_model_is_blocked():
    db = _session()
    try:
        brand = EquipmentBrand(name="علامة مستخدمة", is_active=True)
        category = EquipmentCategory(
            name="فئة اختبار العلامة",
            code="brand-delete-test",
            is_system=False,
        )
        equipment_type = EquipmentType(
            name="نوع اختبار العلامة",
            measurement_unit="km",
            category=category,
        )
        model = EquipmentModel(
            name="طراز اختبار العلامة",
            equipment_type=equipment_type,
            brand=brand,
            mobility_type="mobile",
            requires_driver=True,
        )
        db.add_all([brand, category, equipment_type, model])
        db.commit()
        db.refresh(brand)

        with pytest.raises(ValueError, match="مرتبطة بطرازات"):
            services.delete_brand(db, brand)

        assert services.get_brand(db, brand.id) is not None
    finally:
        db.close()
