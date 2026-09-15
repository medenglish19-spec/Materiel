import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModelSpecDefinition,
    EquipmentType,
)
from app.modules.equipment_types.presenters import model_editor_payload
from app.modules.equipment_types.schemas import EquipmentModelCreate, SpecValueInput, TirePositionInput
from app.modules.equipment_types import services
from app.modules.tires.models import TireModelSize, TirePosition


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


def test_model_editor_full_lifecycle_persists_nested_configuration():
    db = _session()
    try:
        category = EquipmentCategory(name="مركبات", code="VEH", is_system=False)
        brand = EquipmentBrand(name="اختبار", is_active=True)
        db.add_all([category, brand])
        db.flush()
        equipment_type = EquipmentType(
            name="مركبة اختبار",
            measurement_unit="km",
            category_id=category.id,
        )
        spec = EquipmentModelSpecDefinition(
            name="سعة المحرك",
            data_type="number",
            unit="cc",
            options=None,
            sort_order=0,
        )
        db.add_all([equipment_type, spec])
        db.flush()

        created = services.create_model(
            db,
            EquipmentModelCreate(
                name="طراز اختبار",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
                has_tires=True,
                tire_positions_required=2,
                axle_count=1,
                tire_size="265/65R17",
                has_batteries=True,
                battery_count_required=2,
                battery_capacity_ah=100,
                battery_voltage_v=12,
                mobility_type="mobile",
                requires_driver=True,
                positions=[
                    TirePositionInput(axle_number=1, side="left", position_type="single", description="أمامي"),
                    TirePositionInput(axle_number=1, side="right", position_type="single", description="أمامي"),
                ],
                sizes=["265/65R17", "285/60R18"],
                specs=[SpecValueInput(definition_id=spec.id, value="4500")],
            ),
        )
        payload = model_editor_payload(db, created)
        json.dumps(payload, ensure_ascii=False)
        assert len(payload["positions"]) == 2
        assert payload["sizes"] == ["265/65R17", "285/60R18"]
        assert payload["specs"] == [{"definition_id": spec.id, "value": "4500"}]
        assert payload["has_batteries"] is True
        assert payload["battery_count_required"] == 2

        first_position = payload["positions"][0]
        updated = services.update_model(
            db,
            created,
            EquipmentModelCreate(
                name="طراز اختبار محدث",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
                has_tires=True,
                tire_positions_required=1,
                axle_count=1,
                tire_size="265/65R17",
                has_batteries=True,
                battery_count_required=1,
                battery_capacity_ah=110,
                battery_voltage_v=12,
                mobility_type="mobile",
                requires_driver=False,
                positions=[
                    TirePositionInput(
                        id=first_position["id"],
                        axle_number=1,
                        side="left",
                        position_type="single",
                        description="محدث",
                    )
                ],
                sizes=["265/65R17"],
                specs=[SpecValueInput(definition_id=spec.id, value="4600")],
            ),
        )
        db.expire_all()
        reloaded = services.get_model(db, updated.id)
        payload2 = model_editor_payload(db, reloaded)
        assert payload2["name"] == "طراز اختبار محدث"
        assert len(payload2["positions"]) == 1
        assert payload2["positions"][0]["description"] == "محدث"
        assert payload2["sizes"] == ["265/65R17"]
        assert payload2["specs"] == [{"definition_id": spec.id, "value": "4600"}]
        assert payload2["requires_driver"] is False
        assert payload2["battery_count_required"] == 1

    finally:
        db.close()


def test_nested_tire_configuration_is_owned_by_model():
    assert TirePosition.equipment_model_id.name == "equipment_model_id"
    assert TireModelSize.equipment_model_id.name == "equipment_model_id"
