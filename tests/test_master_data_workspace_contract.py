from pathlib import Path
import inspect

from app.modules.equipment_types.router import create_model_form


def _template() -> str:
    return Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


def test_model_editor_is_hierarchical_and_excel_grid_oriented():
    template = _template()
    assert "window.scrollTo" not in template
    for label in ("الطرازات", "البيانات الأساسية", "الإطارات", "مواضع الإطارات", "المقاسات المعتمدة", "البطاريات", "الخصائص التابعة"):
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
    assert "editModel(modelNode.dataset.model,treeAdd.dataset.treeAdd==='position'?'positions':'sizes')" in template
    assert "treeAdd.dataset.treeAdd==='position'?addPos():addSize();" in template


def test_model_editor_requires_driver_defaults_to_false_in_post_form():
    parameter = inspect.signature(create_model_form).parameters["requires_driver"]
    assert parameter.default.default is False
