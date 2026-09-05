import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory
from app.modules.equipment_types.schemas import EquipmentModelCreate, EquipmentTypeCreate
from app.modules.equipment_types import services


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_equipment_classification_hierarchy_and_model_brand():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        category = EquipmentCategory(
            name="المركبات الثقيلة",
            code="HEAVY",
            sort_order=20,
            is_system=True,
        )
        brand = EquipmentBrand(name="Mercedes-Benz")
        db.add_all([category, brand])
        db.flush()

        equipment_type = services.create_type(
            db,
            EquipmentTypeCreate(
                name="شاحنات",
                measurement_unit="km",
                category_id=category.id,
                theoretical_quantity=12,
            ),
        )
        model = services.create_model(
            db,
            EquipmentModelCreate(
                name="Actros 3340",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
            ),
        )
        second_model = services.create_model(
            db,
            EquipmentModelCreate(
                name="Actros 4140",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
            ),
        )

        assert equipment_type.category_id == category.id
        assert equipment_type.theoretical_quantity == 12
        assert model.brand_id == brand.id
        assert model.equipment_type_id == equipment_type.id
        assert second_model.equipment_type_id == equipment_type.id
        assert not hasattr(model, "theoretical_quantity")
        assert not hasattr(second_model, "theoretical_quantity")

        services.set_type_theoretical_quantity(db, equipment_type, 15)
        assert equipment_type.theoretical_quantity == 15
        assert second_model.equipment_type_id == equipment_type.id

        with pytest.raises(ValueError, match="فئة العتاد مطلوبة"):
            services.set_type_category(db, equipment_type, None)
        assert equipment_type.category_id == category.id
    finally:
        db.close()
