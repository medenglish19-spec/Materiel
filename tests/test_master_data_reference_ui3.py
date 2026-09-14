from pathlib import Path


def test_master_data_ui_contains_reference_management_surface():
    text = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    assert "/equipment-types/brands/create" in text
    assert "/equipment-types/categories/create" in text
    assert "data-search" in text
    assert "تعديل" in text
    assert "تجميد" in text
