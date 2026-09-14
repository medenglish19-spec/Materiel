from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment import services as equipment_services
from app.modules.equipment_types.models import EquipmentBrand, EquipmentModel, EquipmentType
from app.modules.equipment_types import services as model_services
from app.modules.tires.models import Tire, TireMovement, TirePosition


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def test_model_cannot_be_deleted_while_equipment_uses_it():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع حماية الطراز", measurement_unit="km")
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز محمي", equipment_type_id=equipment_type.id)
        db.add(model); db.flush()
        equipment = Equipment(asset_code="MODEL-GUARD-1", equipment_type_id=equipment_type.id, equipment_model_id=model.id)
        db.add(equipment); db.commit()
        with pytest.raises(ValueError, match="لا يمكن حذف طراز مرتبط بعتاد مسجل"):
            model_services.delete_model(db, model)
        assert db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first() is not None
        assert db.query(Equipment).filter(Equipment.id == equipment.id).first() is not None
    finally:
        db.close()


def test_equipment_model_cannot_change_while_tire_is_installed():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع إطارات حماية", measurement_unit="km")
        db.add(equipment_type); db.flush()
        model_a = EquipmentModel(name="طراز الإطارات الحالي", equipment_type_id=equipment_type.id, has_tires=True, tire_positions_required=1, tire_size="315/80R22.5")
        model_b = EquipmentModel(name="طراز الإطارات البديل", equipment_type_id=equipment_type.id, has_tires=True, tire_positions_required=1, tire_size="12R22.5")
        db.add_all([model_a, model_b]); db.flush()
        equipment = Equipment(asset_code="TIRE-MODEL-GUARD-1", equipment_type_id=equipment_type.id, equipment_model_id=model_a.id)
        position = TirePosition(equipment_model_id=model_a.id, code="GUARD-POS-1", name="موضع اختبار", axle_number=1, side="left", position_type="single", sort_order=1)
        tire = Tire(serial_number="GUARD-TIRE-1", size="315/80R22.5", expiry_date=date(2030, 1, 1))
        db.add_all([equipment, position, tire]); db.flush()
        db.add(TireMovement(tire_id=tire.id, movement_date=date(2026, 9, 1), movement_datetime=datetime(2026, 9, 1, 10), movement_type="install", equipment_id=equipment.id, position_id=position.id)); db.commit()
        with pytest.raises(ValueError, match="لا يمكن تغيير طراز العتاد بينما توجد إطارات مركبة عليه"):
            equipment_services.update_equipment(db, equipment, EquipmentUpdate(equipment_model_id=model_b.id))
        db.refresh(equipment); assert equipment.equipment_model_id == model_a.id
    finally:
        db.close()


def test_model_can_be_deleted_after_equipment_is_no_longer_linked():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع حذف آمن", measurement_unit="km")
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز قابل للحذف", equipment_type_id=equipment_type.id)
        db.add(model); db.commit()
        model_services.delete_model(db, model)
        assert db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first() is None
    finally:
        db.close()


def test_equipment_type_cannot_be_deleted_while_models_use_it():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع محمي", measurement_unit="km")
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز تابع", equipment_type_id=equipment_type.id)
        db.add(model); db.commit()
        with pytest.raises(ValueError, match="لا يمكن حذف نوع عتاد مرتبط بطرازات مسجلة"):
            model_services.delete_type(db, equipment_type)
        assert db.query(EquipmentType).filter(EquipmentType.id == equipment_type.id).first() is not None
        assert db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first() is not None
    finally:
        db.close()


def test_model_cannot_be_deleted_while_tire_configuration_exists():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع إعدادات إطارات", measurement_unit="km")
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز إعدادات محمية", equipment_type_id=equipment_type.id, has_tires=True, tire_positions_required=1, tire_size="315/80R22.5")
        db.add(model); db.flush()
        position = TirePosition(equipment_model_id=model.id, code="CONFIG-GUARD-POS-1", name="موضع إعدادات محمي", axle_number=1, side="left", position_type="single", sort_order=1)
        db.add(position); db.commit()
        with pytest.raises(ValueError, match="لا يمكن حذف طراز يحتوي على إعدادات إطارات"):
            model_services.delete_model(db, model)
        assert db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first() is not None
        assert db.query(TirePosition).filter(TirePosition.id == position.id).first() is not None
    finally:
        db.close()


def test_frozen_type_stays_editable_but_blocks_new_model_and_new_equipment():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع غير معتمد", measurement_unit="km", theoretical_quantity=1, is_frozen=True)
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز قديم", equipment_type_id=equipment_type.id)
        db.add(model); db.commit()

        model_services.set_type_theoretical_quantity(db, equipment_type, 5)
        assert equipment_type.theoretical_quantity == 5
        with pytest.raises(ValueError, match="نوع العتاد مجمد"):
            model_services.create_model(db, type("Data", (), {"equipment_type_id": equipment_type.id, "brand_id": 999, "name": "طراز جديد", "has_tires": False, "tire_positions_required": 0, "tire_size": None, "has_batteries": False, "battery_count_required": 0, "battery_capacity_ah": None, "battery_voltage_v": None, "mobility_type": "mobile", "requires_driver": True})())
        with pytest.raises(ValueError, match="نوع العتاد مجمد"):
            equipment_services.create_equipment(db, EquipmentCreate(equipment_type_id=equipment_type.id, equipment_model_id=model.id))
    finally:
        db.close()


def test_frozen_model_stays_editable_but_blocks_new_equipment():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع نشط", measurement_unit="km")
        db.add(equipment_type); db.flush()
        brand = EquipmentBrand(name="علامة اختبار")
        db.add(brand); db.flush()
        model = EquipmentModel(name="طراز غير معتمد", equipment_type_id=equipment_type.id, brand_id=brand.id, is_frozen=True)
        db.add(model); db.commit()

        model_services.set_model_brand(db, model, brand.id)
        with pytest.raises(ValueError, match="طراز العتاد مجمد"):
            equipment_services.create_equipment(db, EquipmentCreate(equipment_type_id=equipment_type.id, equipment_model_id=model.id))
    finally:
        db.close()


def test_existing_equipment_can_continue_when_type_or_model_is_frozen():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع مستمر", measurement_unit="km", is_frozen=True)
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز مستمر", equipment_type_id=equipment_type.id, is_frozen=True)
        db.add(model); db.flush()
        equipment = Equipment(asset_code="FROZEN-EXISTING-1", equipment_type_id=equipment_type.id, equipment_model_id=model.id)
        db.add(equipment); db.commit()

        equipment_services.update_equipment(db, equipment, EquipmentUpdate(notes="تشغيل مستمر"))
        equipment_services.update_technical_condition(db, equipment.id, "ready")
        equipment_services.update_operational_status(db, equipment.id, "available")
        db.refresh(equipment)
        assert equipment.notes == "تشغيل مستمر"
        assert equipment.technical_condition == "ready"
        assert equipment.operational_status == "available"
    finally:
        db.close()


def test_unfreezing_restores_new_equipment_adoption():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع قابل لإعادة الاعتماد", measurement_unit="km", is_frozen=True)
        db.add(equipment_type); db.flush()
        model = EquipmentModel(name="طراز قابل لإعادة الاعتماد", equipment_type_id=equipment_type.id, is_frozen=True)
        db.add(model); db.commit()

        model_services.set_type_frozen(db, equipment_type, False)
        model_services.set_model_frozen(db, model, False)
        equipment = equipment_services.create_equipment(db, EquipmentCreate(equipment_type_id=equipment_type.id, equipment_model_id=model.id))
        assert equipment.equipment_model_id == model.id
    finally:
        db.close()
