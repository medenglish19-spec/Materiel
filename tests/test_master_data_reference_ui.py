from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html")


def test_master_data_ui_contains_reference_management_entry_points():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "إضافة علامة تجارية جديدة" in text or "/equipment-types/brands/create" in text
    assert "/equipment-types/categories/create" in text
    assert "/equipment-types/{category_id}/update" not in text
    assert "data-search" in text
    assert "تعديل" in text
    assert "تجميد" in text
