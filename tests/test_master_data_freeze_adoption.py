import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment import services as equipment_services
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentUpdate
from app.modules.equipment_types.models import EquipmentModel, EquipmentType

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_existing_equipment_cannot_be_reassigned_into_frozen_type():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        active_type = EquipmentType(name="نوع حالي", measurement_unit="km")
        frozen_type = EquipmentType(name="نوع موقوف", measurement_unit="km", is_frozen=True)
        db.add_all([active_type, frozen_type]); db.flush()
        current_model = EquipmentModel(name="طراز حالي", equipment_type_id=active_type.id)
        frozen_model = EquipmentModel(name="طراز موقوف", equipment_type_id=frozen_type.id, is_frozen=True)
        db.add_all([current_model, frozen_model]); db.flush()
        equipment = Equipment(asset_code="FREEZE-REASSIGN-1", equipment_type_id=active_type.id, equipment_model_id=current_model.id)
        db.add(equipment); db.commit()

        with pytest.raises(ValueError, match="نوع العتاد مجمد"):
            equipment_services.update_equipment(
                db,
                equipment,
                EquipmentUpdate(equipment_type_id=frozen_type.id, equipment_model_id=frozen_model.id),
            )
        db.refresh(equipment)
        assert equipment.equipment_type_id == active_type.id
        assert equipment.equipment_model_id == current_model.id
    finally:
        db.close()
