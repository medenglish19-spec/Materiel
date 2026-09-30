from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html")
NAV_JS = Path("static/js/master-data-nav.js")


def test_master_data_ui_contains_reference_management_entry_points():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "مركز البيانات الأساسية" in text
    # قرار المستخدم (2026-09-30): اختفت الشجرة، وصار الفئة عنوانًا رئيسيًا داخل شريحة.
    assert "شجرة مركز البيانات" not in text
    assert "فئات العتاد" in text
    assert "الطرازات" in text
    assert "الخصائص" in text
    assert "positions_json" in text
    assert "sizes_json" in text
    assert "specs_json" in text


def test_master_data_ui_preserves_hierarchy_actions_and_measurement_unit_dropdown():
    template = TEMPLATE.read_text(encoding="utf-8")
    nav_js = NAV_JS.read_text(encoding="utf-8")

    # The existing measurement-unit control remains a dropdown with the established values.
    assert '<select name="measurement_unit" required>' in template
    assert '<option value="km">كم</option>' in template
    assert '<option value="hours">ساعات</option>' in template

    # The category/type/model hierarchy and its existing CRUD entry points are wired into the sheets.
    assert 'data-ref-item="category"' in template
    assert 'data-ref-item="type"' in template
    assert 'data-model-row="{{ m.id }}"' in template
    assert 'data-new-type-for-category="{{ c.id }}"' in template
    assert 'data-new-model-for-type="{{ t.id }}"' in template
    assert "action.dataset.newTypeForCategory" in nav_js
    assert "action.dataset.newModelForType" in nav_js
    assert "data-edit" in nav_js
    assert "data-delete" in nav_js
    assert "/equipment-types/categories/" in nav_js
    assert "/equipment-types/" in nav_js
    assert "/equipment-types/models/" in nav_js
