from pathlib import Path


ROOT = Path(__file__).parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_equipment_pages_use_only_the_configured_meter_unit():
    detail = read("app/modules/equipment/templates/equipment_detail.html")
    listing = read("app/modules/equipment/templates/equipment_list.html")
    meters = read("app/modules/equipment/templates/equipment_meters.html")

    assert "عداد الساعات" in detail and "عداد الكيلومترات" in detail
    assert "measurement_unit == 'hours'" in detail
    assert "class=\"col-meter\"" in listing
    assert "class=\"col-odo\"" not in listing
    assert "class=\"col-hours\"" not in listing
    assert "item.current_hours if item.current_hours is not none else '—'" in listing
    assert "item.current_odometer if item.current_odometer is not none else '—'" in listing
    assert "measurement_unit == 'hours'" in meters
    assert "<th>الكيلومترات</th>" not in meters
    assert "<th>الساعات</th>" not in meters
    assert "id=\"editOdometerField\"" in meters and "id=\"editHoursField\"" in meters


def test_maintenance_conditions_library_keeps_the_operation_level_warning_fields():
    rules = read("app/modules/maintenance/templates/maintenance_rules_model_only.html")

    # حقول الإنذار الموحّدة على مستوى العملية تبقى في المكتبة.
    assert "إنذار قبل كم" in rules
    assert "إنذار قبل أيام" in rules
    # المكتبة العامة لم تعد تختار طرازًا ولا تحرّر شروطًا لكل طراز.
    assert "equipment_model_conditions" not in rules
    assert "editorModelsBody" not in rules
    # Updated page title
    assert "مكتبة عمليات الصيانة" in rules
