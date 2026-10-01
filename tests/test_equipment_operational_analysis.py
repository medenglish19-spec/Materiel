from datetime import date
from types import SimpleNamespace

from app.modules.equipment.operational_analysis import build_operational_analysis


def test_operational_analysis_counts_fault_and_maintenance_burden():
    item = SimpleNamespace(
        id=1,
        registration_number="2015132131",
        equipment_model=SimpleNamespace(name="HIGER"),
    )
    faults = [
        SimpleNamespace(equipment_id=1, status="open", severity="high", exploitation_impact="prohibited", fault_type=None, reported_date=date(2026, 1, 10)),
        SimpleNamespace(equipment_id=1, status="closed", severity="low", exploitation_impact="none", fault_type=None, reported_date=date(2026, 2, 10)),
    ]
    records = [
        SimpleNamespace(equipment_id=1, is_scheduled=True, maintenance_date=date(2026, 1, 5)),
        SimpleNamespace(equipment_id=1, is_scheduled=False, maintenance_date=date(2026, 2, 5)),
    ]

    result = build_operational_analysis([item], faults, records)
    row = result["rows"][0]

    assert row["fault_count"] == 2
    assert row["open_fault_count"] == 1
    assert row["severe_fault_count"] == 1
    assert row["prohibited_fault_count"] == 1
    assert row["maintenance_count"] == 2
    assert row["scheduled_maintenance_count"] == 1
    assert result["totals"]["open_faults"] == 1
