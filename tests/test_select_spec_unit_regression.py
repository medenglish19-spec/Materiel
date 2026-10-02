# Regression coverage: a select technical property must show only the selected
# option. Legacy seed migrations unpacked the option list into `unit`, so pages
# that append `spec.definition.unit` rendered the whole option list after the
# chosen value (e.g. "حافلة بيك أب,سيدان,دفع رباعي,شاحنة,حافلة,خاص").
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.users.models import User
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentModelSpecValue,
    EquipmentType,
)

# Register all project model modules so SQLAlchemy can resolve cross-module
# relationships in the isolated test schema.
from app.modules.batteries import models as _batteries_models  # noqa: F401
from app.modules.faults_repairs import models as _faults_repairs_models  # noqa: F401
from app.modules.fuel import models as _fuel_models  # noqa: F401
from app.modules.maintenance import models as _maintenance_models  # noqa: F401
from app.modules.meter_readings import models as _meter_readings_models  # noqa: F401
from app.modules.missions import models as _missions_models  # noqa: F401
from app.modules.tires import models as _tires_models  # noqa: F401
from app.modules.equipment_types.schemas import (
    EquipmentModelCreate,
    SpecDefinitionCreate,
    SpecValueInput,
)
from app.modules.equipment_types import services

# Load the full application model registry before Base.metadata.create_all().
from web.main import app as _app  # noqa: F401

ROOT = Path(__file__).parents[1]
GEAR_OPTIONS = "يدوي,أوتوماتيكي,نصف أوتوماتيكي,CVT"
DRIVE_OPTIONS = "2x4,4x4,6x6"

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Session = sessionmaker(bind=engine)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def newdb():
    # Register cross-module audit FK target before creating the isolated schema.
    _ = (User, Equipment)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def base(db):
    category = EquipmentCategory(name="sel-cat", code="SEL", is_system=True)
    brand = EquipmentBrand(name="sel-brand", is_active=True)
    db.add_all([category, brand])
    db.flush()
    kind = EquipmentType(name="sel-type", measurement_unit="km", category_id=category.id)
    db.add(kind)
    db.flush()
    return kind, brand


def model_data(kind, brand, specs=None, name="sel-model"):
    return EquipmentModelCreate(
        name=name, equipment_type_id=kind.id, brand_id=brand.id, specs=specs or []
    )


# --- the option list must never be stored as the unit -----------------------

def test_select_definition_drops_option_list_stored_as_unit():
    db = newdb()
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="gear", data_type="select", unit=GEAR_OPTIONS, options=GEAR_OPTIONS)
    )
    assert definition.unit is None
    assert definition.options == GEAR_OPTIONS
    db.close()


def test_select_definition_drops_option_list_unit_pasted_with_spaces():
    db = newdb()
    definition = services.create_spec_definition(
        db,
        SpecDefinitionCreate(
            name="body",
            data_type="select",
            unit="يدوي, أوتوماتيكي , نصف أوتوماتيكي ,CVT",
            options=GEAR_OPTIONS,
        ),
    )
    assert definition.unit is None
    db.close()


def test_number_and_text_units_are_preserved():
    db = newdb()
    year = services.create_spec_definition(
        db, SpecDefinitionCreate(name="year", data_type="number", unit="سنة")
    )
    note = services.create_spec_definition(
        db, SpecDefinitionCreate(name="note", data_type="text", unit="ملاحظة")
    )
    assert year.unit == "سنة"
    assert note.unit == "ملاحظة"
    db.close()


def test_select_keeps_a_unit_that_is_not_the_option_list():
    # Anything that is not provably a copy of the option list is left alone.
    db = newdb()
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="gauge", data_type="select", unit="وحدة", options=GEAR_OPTIONS)
    )
    assert definition.unit == "وحدة"
    db.close()


# --- only the selected value may be sent and stored --------------------------

def test_select_value_rejects_the_whole_option_list():
    db = newdb()
    kind, brand = base(db)
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="gear-list", data_type="select", options=GEAR_OPTIONS)
    )
    with pytest.raises(ValueError, match="إحدى"):
        services.create_model(
            db, model_data(kind, brand, [SpecValueInput(definition_id=definition.id, value=GEAR_OPTIONS)])
        )
    db.rollback()
    assert db.query(EquipmentModelSpecValue).count() == 0
    db.close()


def test_select_value_rejects_selected_value_attached_to_option_list():
    db = newdb()
    kind, brand = base(db)
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="drive-list", data_type="select", options=DRIVE_OPTIONS)
    )
    with pytest.raises(ValueError, match="إحدى"):
        services.create_model(
            db,
            model_data(
                kind, brand, [SpecValueInput(definition_id=definition.id, value="2x4 2x4,4x4,6x6")]
            ),
        )
    db.rollback()
    assert db.query(EquipmentModelSpecValue).count() == 0
    db.close()


def test_select_value_stores_only_the_selected_option():
    db = newdb()
    kind, brand = base(db)
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="gear-one", data_type="select", options=GEAR_OPTIONS)
    )
    model = services.create_model(
        db, model_data(kind, brand, [SpecValueInput(definition_id=definition.id, value="أوتوماتيكي")])
    )
    row = db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=model.id).one()
    assert row.value == "أوتوماتيكي"
    db.close()


def test_update_model_rejects_option_list_as_value():
    db = newdb()
    kind, brand = base(db)
    definition = services.create_spec_definition(
        db, SpecDefinitionCreate(name="gear-edit", data_type="select", options=GEAR_OPTIONS)
    )
    model = services.create_model(
        db, model_data(kind, brand, [SpecValueInput(definition_id=definition.id, value="يدوي")], "edit-me")
    )
    with pytest.raises(ValueError, match="إحدى"):
        services.update_model(
            db,
            model,
            model_data(
                kind, brand, [SpecValueInput(definition_id=definition.id, value=GEAR_OPTIONS)], "edit-me"
            ),
        )
    db.rollback()
    assert db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=model.id).one().value == "يدوي"
    db.close()


# --- the view must never append a unit to a select value ---------------------

def test_equipment_detail_hides_unit_for_select_properties():
    detail = read("app/modules/equipment/templates/equipment_detail.html")
    assert "spec.definition.data_type != 'select' and spec.definition.unit" in detail


def test_master_data_labels_hide_unit_for_select_properties():
    workspace = read("app/modules/equipment_types/templates/master_data_workspace.html")
    listing = read("app/modules/equipment/templates/equipment_list.html")
    # picker + editor + view rows in the workspace, and the filter dropdown
    assert workspace.count("def.data_type!=='select'&&def.unit") == 3
    assert listing.count("def.data_type!=='select'&&def.unit") == 1
    # no label may append the unit without the select guard
    assert "+(def.unit?' (" not in workspace
    assert "+(def.unit?' (" not in listing
