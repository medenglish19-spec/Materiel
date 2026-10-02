"""حماية: التحليل التشغيلي لا ينهار على عتاد بلا حالة مسجّلة.

القراءة بـ getattr تعني «لا تخترع قيمة»، ولا «تCrash» إذا غابت الخاصية.
"""
import inspect
from datetime import date
from types import SimpleNamespace

from app.modules.equipment.operational_analysis import build_operational_analysis


def _item(**over):
    base = dict(
        id=1,
        registration_number="2015132131",
        equipment_model=SimpleNamespace(name="HIGER"),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_missing_state_attributes_yield_none_not_crash():
    row = build_operational_analysis([_item()], [], [])["rows"][0]
    assert row["technical_condition"] is None
    assert row["operational_status"] is None


def test_present_state_attributes_are_reported_verbatim():
    row = build_operational_analysis(
        [_item(technical_condition="ready", operational_status="available")], [], []
    )["rows"][0]
    assert row["technical_condition"] == "ready"
    assert row["operational_status"] == "available"


def test_counts_remain_correct_when_state_is_absent():
    faults = [
        SimpleNamespace(equipment_id=1, status="open", severity="high",
                        exploitation_impact="prohibited", fault_type=None,
                        reported_date=date(2026, 1, 10))
    ]
    records = [
        SimpleNamespace(equipment_id=1, is_scheduled=True,
                        maintenance_date=date(2026, 1, 5))
    ]
    result = build_operational_analysis([_item()], faults, records)
    row = result["rows"][0]
    assert row["fault_count"] == 1
    assert row["open_fault_count"] == 1
    assert row["prohibited_fault_count"] == 1
    assert row["maintenance_count"] == 1
    assert row["scheduled_maintenance_count"] == 1
    assert result["totals"]["faults"] == 1


def test_source_uses_getattr_for_state_fields():
    """حماية صريحة: أي عودة لقراءة مباشرة تنكسر على العتاد الناقص."""
    source = inspect.getsource(build_operational_analysis)
    assert 'getattr(item, "technical_condition", None)' in source
    assert 'getattr(item, "operational_status", None)' in source
    assert "item.technical_condition," not in source
    assert "item.operational_status," not in source
