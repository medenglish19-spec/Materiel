from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html")


def test_master_data_ui_contains_reference_management_entry_points():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "مركز البيانات الأساسية" in text
    assert "شجرة مركز البيانات" in text
    assert "الطرازات" in text
    assert "الخصائص" in text
    assert "positions_json" in text
    assert "sizes_json" in text
    assert "specs_json" in text
