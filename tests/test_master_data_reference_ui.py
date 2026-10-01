from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html")
TREE_JS = Path("static/js/master-data-tree.js")


def test_master_data_ui_contains_reference_management_entry_points():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "مركز البيانات الأساسية" in text
    assert "شجرة مركز البيانات" in text
    assert "الطرازات" in text
    assert "الخصائص" in text
    assert "positions_json" in text
    assert "sizes_json" in text
    assert "specs_json" in text


def test_master_data_ui_preserves_hierarchy_actions_and_measurement_unit_dropdown():
    template = TEMPLATE.read_text(encoding="utf-8")
    tree_js = TREE_JS.read_text(encoding="utf-8")

    # The existing measurement-unit control remains a dropdown with the established values.
    assert '<select name="measurement_unit" required>' in template
    assert '<option value="km">كم</option>' in template
    assert '<option value="hours">ساعات</option>' in template

    # The category/type/model hierarchy and its existing CRUD entry points are wired into the tree.
    assert 'data-ref-item="category"' in template
    assert 'data-ref-item="type"' in template
    assert 'data-model-row="{{ m.id }}"' in template
    assert "data-new-type-for-category" in tree_js
    assert "data-new-model-for-type" in tree_js
    assert "data-tree-edit" in tree_js
    assert "data-tree-delete" in tree_js
    assert "/equipment-types/categories/" in tree_js
    assert "/equipment-types/" in tree_js
    assert "/equipment-types/models/" in tree_js
