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
    assert "item.current_hours or 0" in listing
    assert "item.current_odometer or 0" in listing
    assert "measurement_unit == 'hours'" in meters
    assert "<th>الكيلومترات</th>" not in meters
    assert "<th>الساعات</th>" not in meters
    assert "id=\"editOdometerField\"" in meters and "id=\"editHoursField\"" in meters


def test_maintenance_pages_render_meter_values_with_the_equipment_unit():
    dashboard = read("app/modules/maintenance/templates/maintenance_dashboard.html")
    due = read("app/modules/maintenance/templates/maintenance_due.html")
    rules = read("app/modules/maintenance/templates/maintenance_rules.html")

    for text in (dashboard, due):
        assert "row.unit == 'hours'" in text
        assert "المتبقي بالعداد" in text or "القراءة القادمة" in text
        assert "الكيلومترات المتبقية" not in text

    assert "فترة العداد" in rules
    assert "meter-km-field" in rules
    assert "meter-hours-field" in rules
    assert "syncMeterFields" in rules
