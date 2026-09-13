from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentUpdate
from app.modules.equipment import services as equipment_services
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
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
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="طراز محمي", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()
        equipment = Equipment(
            asset_code="MODEL-GUARD-1",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model.id,
        )
        db.add(equipment)
        db.commit()

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
        db.add(equipment_type)
        db.flush()
        model_a = EquipmentModel(
            name="طراز الإطارات الحالي",
            equipment_type_id=equipment_type.id,
            has_tires=True,
            tire_positions_required=1,
            tire_size="315/80R22.5",
        )
        model_b = EquipmentModel(
            name="طراز الإطارات البديل",
            equipment_type_id=equipment_type.id,
            has_tires=True,
            tire_positions_required=1,
            tire_size="12R22.5",
        )
        db.add_all([model_a, model_b])
        db.flush()

        equipment = Equipment(
            asset_code="TIRE-MODEL-GUARD-1",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_a.id,
        )
        position = TirePosition(
            equipment_model_id=model_a.id,
            code="GUARD-POS-1",
            name="موضع اختبار",
            axle_number=1,
            side="left",
            position_type="single",
            sort_order=1,
        )
        tire = Tire(
            serial_number="GUARD-TIRE-1",
            size="315/80R22.5",
            expiry_date=date(2030, 1, 1),
        )
        db.add_all([equipment, position, tire])
        db.flush()
        movement = TireMovement(
            tire_id=tire.id,
            movement_date=date(2026, 9, 1),
            movement_type="install",
            equipment_id=equipment.id,
            position_id=position.id,
        )
        db.add(movement)
        db.commit()

        with pytest.raises(ValueError, match="لا يمكن تغيير طراز العتاد بينما توجد إطارات مركبة عليه"):
            equipment_services.update_equipment(
                db,
                equipment,
                EquipmentUpdate(equipment_model_id=model_b.id),
            )

        db.refresh(equipment)
        assert equipment.equipment_model_id == model_a.id
    finally:
        db.close()


def test_model_can_be_deleted_after_equipment_is_no_longer_linked():
    db = _fresh_db()
    try:
        equipment_type = EquipmentType(name="نوع حذف آمن", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="طراز قابل للحذف", equipment_type_id=equipment_type.id)
        db.add(model)
        db.commit()

        model_services.delete_model(db, model)

        assert db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first() is None
    finally:
        db.close()
