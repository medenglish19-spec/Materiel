from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html")


def test_master_data_ui_contains_reference_management_entry_points():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "مركز البيانات الأساسية" in text
    assert "محرر الطراز" in text
    assert "id=\"mdSearch\"" in text
    assert "positions_json" in text
    assert "sizes_json" in text
