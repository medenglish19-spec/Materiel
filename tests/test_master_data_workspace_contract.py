import inspect
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.presenters import model_editor_payload
from app.modules.equipment_types.router import create_model_form
from app.modules.equipment_types import services
from app.modules.equipment_types.schemas import EquipmentModelCreate
from web.main import app


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_master_data_routes_are_registered():
    routes = {
        (route.path, tuple(sorted(getattr(route, "methods", None) or ())))
        for route in app.routes
        if getattr(route, "methods", None)
    }
    expected = {
        ("/equipment-types", ("GET",)),
        ("/equipment-types/categories/create", ("POST",)),
        ("/equipment-types/create", ("POST",)),
        ("/equipment-types/brands/create", ("POST",)),
        ("/equipment-types/specs/create", ("POST",)),
        ("/equipment-types/models/create", ("POST",)),
        ("/equipment-types/models/{model_id}/update", ("POST",)),
    }
    assert expected <= routes


def test_model_editor_presenter_is_json_safe_and_contains_reference_chain():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        category = EquipmentCategory(name="الفئة", code="CAT", is_system=False)
        brand = EquipmentBrand(name="العلامة", is_active=True)
        db.add_all([category, brand])
        db.flush()
        equipment_type = EquipmentType(name="النوع", measurement_unit="km", category_id=category.id)
        db.add(equipment_type)
        db.flush()
        model = services.create_model(
            db,
            EquipmentModelCreate(
                name="الطراز",
                equipment_type_id=equipment_type.id,
                brand_id=brand.id,
                requires_driver=False,
            ),
        )
        payload = model_editor_payload(db, model)
        json.dumps(payload, ensure_ascii=False)
        assert payload["category_id"] == category.id
        assert payload["equipment_type_id"] == equipment_type.id
        assert payload["brand_id"] == brand.id
        assert payload["requires_driver"] is False
    finally:
        db.close()


def test_requires_driver_unchecked_form_defaults_to_false():
    parameter = inspect.signature(create_model_form).parameters["requires_driver"]
    assert parameter.default.default is False


def test_model_editor_has_no_new_model_scroll_and_has_category_selector():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    assert 'id="modelCategory"' in template
    assert "window.scrollTo" not in template
    assert 'data-category="{{ type.category_id or \'\' }}"' in template
    assert "|tojson" in template
    assert "model|tojson" not in template
