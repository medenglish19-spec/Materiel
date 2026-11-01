from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.equipment import services
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment_types.models import EquipmentModel, EquipmentType


def test_equipment_image_storage_validates_and_removes_files(tmp_path, monkeypatch):
    module_path = tmp_path / "app" / "modules" / "equipment" / "services.py"
    module_path.parent.mkdir(parents=True)
    module_path.touch()
    monkeypatch.setattr(services, "__file__", str(module_path))

    payload = BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(payload, format="PNG")
    image_url = services.store_equipment_image(payload.getvalue(), "vehicle.png")
    stored = tmp_path / "static" / "uploads" / "equipment" / image_url.rsplit("/", 1)[-1]

    assert image_url.startswith("/static/uploads/equipment/")
    assert stored.is_file()
    services.remove_equipment_image(image_url)
    assert not stored.exists()

    with pytest.raises(ValueError, match="نوع الصورة غير مدعوم"):
        services.store_equipment_image(payload.getvalue(), "vehicle.svg")


def test_equipment_image_url_is_saved_replaced_and_cleared():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        equipment_type = EquipmentType(name="نوع صورة العتاد", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="طراز صورة العتاد", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()

        equipment = services.create_equipment(
            db,
            EquipmentCreate(
                equipment_type_id=equipment_type.id,
                equipment_model_id=model.id,
                registration_number="IMAGE-REG-1",
                image_url="/static/uploads/equipment/first.png",
            ),
        )
        assert equipment.image_url == "/static/uploads/equipment/first.png"

        services.update_equipment(
            db,
            equipment,
            EquipmentUpdate(image_url="/static/uploads/equipment/second.png"),
        )
        assert equipment.image_url == "/static/uploads/equipment/second.png"

        services.update_equipment(db, equipment, EquipmentUpdate(image_url=None))
        assert equipment.image_url is None

        with pytest.raises(ValueError, match="مسار صورة العتاد غير صالح"):
            services.update_equipment(db, equipment, EquipmentUpdate(image_url="https://example.invalid/photo.png"))
    engine.dispose()
