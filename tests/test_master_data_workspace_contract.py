from pathlib import Path
import inspect

from app.modules.equipment_types.presenters import model_editor_payload
from app.modules.equipment_types.router import create_model_form


def _template() -> str:
    return Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


def _tree_script() -> str:
    return Path("static/js/master-data-tree.js").read_text(encoding="utf-8")


def test_model_editor_is_hierarchical_and_excel_grid_oriented():
    template = _template()
    assert "window.scrollTo" not in template
    for label in ("الطرازات", "البيانات الأساسية", "الإطارات", "مواضع الإطارات", "المقاسات المعتمدة", "البطاريات", "الخصائص التقنية"):
        assert label in template
    for element_id in ("positionsBody", "sizesBody", "specRows", "modelForm"):
        assert f'id="{element_id}"' in template
    assert "positions_json" in template
    assert "sizes_json" in template
    assert "specs_json" in template
    assert "|tojson" in template


def test_model_tree_exposes_inline_tire_creation_actions():
    template = _template()
    assert 'data-tree-add="position"' in template
    assert 'data-tree-add="size"' in template
    script = _tree_script()
    assert "editModel" in script
    assert "addPos" in script
    assert "addSize" in script


def test_tree_add_controls_route_to_the_existing_create_workflows():
    script = _tree_script()
    assert 'event.target.closest(\'[data-add],[data-new-ref]\')' in script
    assert "const kind = add.dataset.add || add.dataset.newRef;" in script
    assert "if (kind === 'model') openModelCreate(action.dataset.newModelForType);" in script
    assert "else if (typeof refPanel === 'function') refPanel(kind);" in script
    assert "openTypeCreate(addForCategory.dataset.newTypeForCategory)" in script
    assert "openModelCreate(addForType.dataset.newModelForType)" in script


def test_model_workspace_loads_every_model_field_from_its_own_payload():
    script = _template()
    for expression in (
        "const d=DATA[String(id)]||DATA[id]||{}",
        "$('modelName').value=d.name||''",
        "$('modelCategory').value=d.category_id??''",
        "$('modelType').value=d.equipment_type_id??''",
        "$('modelBrand').value=d.brand_id??''",
        "$('hasTires').checked=!!d.has_tires",
        "$('hasBatteries').checked=!!d.has_batteries",
        "renderPositions(d.positions||d.master?.positions||[])",
        "renderSizes(d.sizes||d.master?.sizes||[])",
        "renderSpecEditor(d)",
    ):
        assert expression in script



def test_new_model_creation_is_scoped_to_selected_type_and_loads_applicable_specs():
    template = _template()
    assert "data-new-model-for-type=\"{{ t.id }}\"" in template
    assert "function refreshModelTypeContext(typeId)" in template
    assert "$('modelType').onchange=()=>refreshModelTypeContext($('modelType').value)" in template
    assert "const context={equipment_type_id:id?Number(id):0" in template


def test_brand_is_optional_but_can_be_added_from_model_editor():
    template = _template()
    assert 'id="modelBrand" name="brand_id"' in template
    assert 'id="addBrandFromModel"' in template
    assert 'value="">بدون علامة تجارية</option>' in template
    assert "BRANDS[String(d.brand_id)]||'بدون علامة تجارية'" in template


def test_model_editor_payload_is_model_scoped_for_tires_and_specs():
    source = inspect.getsource(model_editor_payload)
    assert "TirePosition.equipment_model_id == model.id" in source
    assert "TireModelSize.equipment_model_id == model.id" in source
    assert "for value in model.spec_values" in source
    assert '"equipment_type_id": model.equipment_type_id' in source


def test_model_editor_requires_driver_defaults_to_false_in_post_form():
    parameter = inspect.signature(create_model_form).parameters["requires_driver"]
    assert parameter.default.default is False


def test_model_editor_payload_contains_model_scoped_battery_configuration():
    source = inspect.getsource(model_editor_payload)
    for field in (
        '"has_batteries": model.has_batteries',
        '"battery_count_required": model.battery_count_required',
        '"battery_capacity_ah": model.battery_capacity_ah',
        '"battery_voltage_v": model.battery_voltage_v',
    ):
        assert field in source


def test_model_editor_form_preserves_battery_configuration_fields():
    template = _template()
    for field in (
        'name="has_batteries"',
        'name="battery_count_required"',
        'name="battery_capacity_ah"',
        'name="battery_voltage_v"',
    ):
        assert field in template
    router_source = inspect.getsource(create_model_form)
    for field in (
        "has_batteries:bool=Form(False)",
        "battery_count_required:int=Form(0)",
        "battery_capacity_ah:str=Form(\"\")",
        "battery_voltage_v:str=Form(\"\")",
    ):
        assert field in router_source
