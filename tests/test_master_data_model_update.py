import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types import services
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel
from app.modules.equipment_types.schemas import EquipmentModelCreate, EquipmentTypeCreate


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def _seed(db):
    category = EquipmentCategory(name="فئة اختبار Master Data", code="MD-TEST")
    brand = EquipmentBrand(name="علامة اختبار Master Data")
    second_brand = EquipmentBrand(name="علامة ثانية Master Data")
    db.add_all([category, brand, second_brand])
    db.flush()
    equipment_type = services.create_type(
        db,
        EquipmentTypeCreate(
            name="نوع اختبار Master Data",
            measurement_unit="km",
            category_id=category.id,
            theoretical_quantity=10,
        ),
    )
    second_type = services.create_type(
        db,
        EquipmentTypeCreate(
            name="نوع ثان Master Data",
            measurement_unit="hours",
            category_id=category.id,
        ),
    )
    model = services.create_model(
        db,
        EquipmentModelCreate(
            name="طراز اختبار Master Data",
            equipment_type_id=equipment_type.id,
            brand_id=brand.id,
        ),
    )
    return category, brand, second_brand, equipment_type, second_type, model


def _data(model, *, name=None, type_id=None, brand_id=None, has_tires=False, tire_count=0, tire_size=None, has_batteries=False, battery_count=0, battery_ah=None, battery_v=None):
    return EquipmentModelCreate(
        name=name or model.name,
        equipment_type_id=type_id or model.equipment_type_id,
        brand_id=brand_id or model.brand_id,
        has_tires=has_tires,
        tire_positions_required=tire_count,
        tire_size=tire_size,
        has_batteries=has_batteries,
        battery_count_required=battery_count,
        battery_capacity_ah=battery_ah,
        battery_voltage_v=battery_v,
        mobility_type="mobile",
        requires_driver=True,
    )


def test_model_update_changes_reference_specs_atomically():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        _, _, second_brand, equipment_type, _, model = _seed(db)
        updated = services.update_model(
            db,
            model,
            _data(
                model,
                name="طراز محدث",
                brand_id=second_brand.id,
                has_tires=True,
                tire_count=6,
                tire_size="315/80R22.5",
                has_batteries=True,
                battery_count=2,
                battery_ah=180,
                battery_v=24,
            ),
        )
        assert updated.name == "طراز محدث"
        assert updated.brand_id == second_brand.id
        assert updated.has_tires is True
        assert updated.tire_positions_required == 6
        assert updated.tire_size == "315/80R22.5"
        assert updated.has_batteries is True
        assert updated.battery_count_required == 2
        assert updated.battery_capacity_ah == 180
        assert updated.battery_voltage_v == 24
        assert updated.equipment_type_id == equipment_type.id
    finally:
        db.close()


def test_model_update_rejects_duplicate_and_frozen_models():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        _, brand, second_brand, equipment_type, _, model = _seed(db)
        services.create_model(
            db,
            EquipmentModelCreate(
                name="طراز مكرر",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
            ),
        )
        with pytest.raises(ValueError, match="الطراز موجود مسبقًا"):
            services.update_model(db, model, _data(model, name="طراز مكرر"))

        services.set_model_frozen(db, model, True)
        with pytest.raises(ValueError, match="مجمد"):
            services.update_model(db, model, _data(model, brand_id=second_brand.id))
    finally:
        db.close()


def test_model_update_rejects_moving_a_model_with_linked_equipment():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        _, brand, _, equipment_type, second_type, model = _seed(db)
        db.add(
            Equipment(
                asset_code="MD-TEST-001",
                registration_number="MD-REG-001",
                vin="MD-VIN-001",
                equipment_type_id=equipment_type.id,
                equipment_model_id=model.id,
            )
        )
        db.commit()
        with pytest.raises(ValueError, match="مرتبط بعتاد فعلي"):
            services.update_model(db, model, _data(model, type_id=second_type.id, brand_id=brand.id))
    finally:
        db.close()
