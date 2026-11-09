from pathlib import Path


TEMPLATE = Path(__file__).parents[1] / "app/modules/meter_readings/templates/meter_readings_list.html"


def test_historical_unavailable_reading_is_rendered_red():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "history-table tr:has(.status-danger) .reading" in text
    assert "color:#b91c1c" in text
