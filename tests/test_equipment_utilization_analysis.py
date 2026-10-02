from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.modules.equipment.analytics import build_utilization_analysis


def test_utilization_uses_meter_history_as_distance_source():
    item = SimpleNamespace(
        id=1,
        registration_number="123",
        equipment_model=SimpleNamespace(name="M1"),
        equipment_type=SimpleNamespace(name="حافلة"),
    )
    readings = [
        SimpleNamespace(id=1, equipment_id=1, reading_date=datetime(2026, 1, 1), odometer=1000),
        SimpleNamespace(id=2, equipment_id=1, reading_date=datetime(2026, 2, 1), odometer=1500),
    ]
    missions = [
        SimpleNamespace(equipment_id=1, departure_meter=1100, return_meter=1300),
    ]
    fuel = [
        SimpleNamespace(equipment_id=1, fueling_date=date(2026, 1, 15), quantity=50),
    ]

    result = build_utilization_analysis([item], readings, missions, fuel)

    assert result["totals"]["distance_km"] == Decimal("500")
    assert result["totals"]["mission_distance_km"] == Decimal("200")
    assert result["totals"]["fuel_liters"] == Decimal("50")
    assert result["rows"][0]["fuel_per_100km"] == Decimal("10")


def test_utilization_does_not_invent_distance_without_meter_history():
    item = SimpleNamespace(
        id=1,
        registration_number="123",
        equipment_model=None,
        equipment_type=SimpleNamespace(name="حافلة"),
    )
    mission = SimpleNamespace(equipment_id=1, departure_meter=1000, return_meter=1200)
    fuel = SimpleNamespace(equipment_id=1, fueling_date=date(2026, 1, 15), quantity=40)

    result = build_utilization_analysis([item], [], [mission], [fuel])

    assert result["totals"]["distance_km"] == 0
    assert result["rows"][0]["distance_km"] is None
    assert result["rows"][0]["fuel_per_100km"] is None
