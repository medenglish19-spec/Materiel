import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types import services
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentCategoryCreate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def setup_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def make_model(db):
    category = services.create_category(db, EquipmentCategoryCreate(name="فئة الحماية", code="frozen-guard"))
    equipment_type = services.create_type(db, EquipmentTypeCreate(name="نوع الحماية", measurement_unit="km", category_id=category.id))
    brand = services.create_brand(db, EquipmentBrandCreate(name="علامة الحماية"))
    model = services.create_model(db, EquipmentModelCreate(name="طراز الحماية", equipment_type_id=equipment_type.id, brand_id=brand.id))
    return equipment_type, brand, model


def test_frozen_type_blocks_category_and_theoretical_quantity_shortcuts():
    db = setup_db()
    try:
        equipment_type, _, _ = make_model(db)
        other_category = services.create_category(db, EquipmentCategoryCreate(name="فئة أخرى", code="other-guard"))
        services.set_type_frozen(db, equipment_type, True)
        with pytest.raises(ValueError, match="مجمد"):
            services.set_type_category(db, equipment_type, other_category.id)
        with pytest.raises(ValueError, match="مجمد"):
            services.set_type_theoretical_quantity(db, equipment_type, 12)
    finally:
        db.close()


def test_frozen_model_blocks_brand_and_tire_configuration_shortcuts():
    db = setup_db()
    try:
        equipment_type, brand, model = make_model(db)
        second_brand = services.create_brand(db, EquipmentBrandCreate(name="علامة ثانية"))
        services.set_model_frozen(db, model, True)
        with pytest.raises(ValueError, match="مجمد"):
            services.set_model_brand(db, model, second_brand.id)
        with pytest.raises(ValueError, match="مجمد"):
            services.update_model_tire_configuration(db, model, True, 4, "265/65R17")
        assert db.get(EquipmentModel, model.id).brand_id == brand.id
        assert db.get(EquipmentModel, model.id).has_tires is False
        assert db.get(EquipmentType, equipment_type.id).is_frozen is False
    finally:
        db.close()
