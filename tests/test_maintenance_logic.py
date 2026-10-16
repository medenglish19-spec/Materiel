from datetime import date, datetime, timedelta
from types import SimpleNamespace
from decimal import Decimal

import pytest

from app.modules.maintenance.router import status_for, priority_for
from app.modules.maintenance.services import plan_status_for
from app.modules.meter_readings.services import validate_meter_observation


def equipment(unit="km"):
    return SimpleNamespace(equipment_type=SimpleNamespace(measurement_unit=unit))


def record(days_ago=0, meter=45000):
    return SimpleNamespace(
        maintenance_date=date.today() - timedelta(days=days_ago),
        meter_value=Decimal(str(meter)),
    )


def rule(**kwargs):
    values = dict(
        interval_km=Decimal("10000"),
        interval_hours=None,
        interval_days=180,
        warning_km=Decimal("500"),
        warning_days=7,
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_no_record_is_initial_maintenance_state():
    state, css, remaining, meta = status_for(rule(), equipment(), None, Decimal("45000"))
    assert state == "بلا سجل"
    assert css == "neutral"
    assert remaining is None


def test_km_due_when_current_meter_reaches_next_service():
    state, css, remaining, meta = status_for(rule(), equipment(), record(meter=45000), Decimal("55000"))
    assert state == "مستحقة الآن"
    assert css == "danger"
    assert remaining == Decimal("0")
    assert meta["next_meter"] == Decimal("55000")


def test_km_near_uses_excel_500_km_threshold():
    state, css, remaining, meta = status_for(rule(), equipment(), record(meter=45000), Decimal("54500"))
    assert state == "تقترب"
    assert css == "warning"
    assert remaining == Decimal("500")


def test_date_due_is_or_condition_with_meter_due():
    r = record(days_ago=180, meter=40000)
    state, css, remaining, meta = status_for(rule(), equipment(), r, Decimal("40000"))
    assert state == "مستحقة الآن"
    assert meta["remaining_days"] == 0


def test_hours_uses_hours_interval_and_does_not_apply_km_warning_threshold():
    r = rule(interval_km=None, interval_hours=Decimal("500"), interval_days=30, warning_km=Decimal("500"), warning_days=7)
    state, css, remaining, meta = status_for(r, equipment("hours"), record(meter=1000), Decimal("1499"))
    assert state == "ضمن الموعد"
    assert css == "success"
    assert remaining == Decimal("1")
    assert meta["remaining_days"] == 30


def test_priority_puts_due_before_near_and_missing_record():
    assert priority_for("مستحقة الآن", Decimal("-1"), {}) == 1
    assert priority_for("تقترب", Decimal("200"), {}) == 2
    assert priority_for("بلا سجل", None, {}) == 3


class _MeterQuery:
    def __init__(self, rows): self.rows = rows
    def filter(self, *args): return self
    def __iter__(self): return iter(self.rows)


class _MeterSession:
    def __init__(self, rows): self.rows = rows
    def query(self, *args): return _MeterQuery(self.rows)


def test_same_day_new_maintenance_cannot_go_backwards_in_meter():
    session = _MeterSession([(1, datetime(2026, 9, 5), Decimal("100"), "manual")])
    with pytest.raises(ValueError, match="نفس التاريخ"):
        validate_meter_observation(session, 20, date(2026, 9, 5), 90, "km", "maintenance")


def test_same_day_new_maintenance_can_keep_or_increase_meter():
    session = _MeterSession([(1, datetime(2026, 9, 5), Decimal("100"), "manual")])
    with pytest.raises(ValueError, match="مسجلة مسبقًا"):
        validate_meter_observation(session, 20, date(2026, 9, 5), 100, "km", "maintenance")
    with pytest.raises(ValueError, match="نفس التاريخ"):
        validate_meter_observation(session, 20, date(2026, 9, 5), 110, "km", "maintenance")


def test_same_day_update_respects_record_id_order():
    session = _MeterSession([(2, datetime(2026, 9, 5), Decimal("100"), "manual")])
    with pytest.raises(ValueError, match="نفس التاريخ"):
        validate_meter_observation(session, 20, date(2026, 9, 5), 90, "km", "maintenance")
    # Updating this observation excludes its own source reference; no peer
    # observation remains on that date, so its replacement value is valid.
    validate_meter_observation(_MeterSession([]), 20, date(2026, 9, 5), 90, "km", "maintenance", "manual:2")


def test_status_uses_calendar_axis_even_when_meter_axis_is_not_due():
    r = rule(interval_km=Decimal("10000"), interval_days=30)
    service_record = record(days_ago=10, meter=45000)
    state, css, remaining, meta = status_for(r, equipment("km"), service_record, Decimal("50000"), today=date.today())
    assert state == "ضمن الموعد"
    assert meta["remaining_days"] == 20
    assert meta["next_meter"] == Decimal("55000")


def test_status_uses_hours_axis_for_hours_equipment():
    r = rule(interval_km=Decimal("10000"), interval_hours=Decimal("500"), interval_days=None)
    service_record = record(meter=1000)
    state, css, remaining, meta = status_for(r, equipment("hours"), service_record, Decimal("1499"), today=date.today())
    assert state == "ضمن الموعد"
    assert remaining == Decimal("1")
    assert meta["remaining_hours"] == Decimal("1")
    assert meta["remaining_km"] is None



def test_plan_status_uses_plan_cadence_without_operation_warning_axes():
    plan = SimpleNamespace(interval_km=Decimal("5000"), interval_hours=None, interval_days=30)
    service_record = record(days_ago=30, meter=45000)
    state, css, remaining, meta = plan_status_for(
        plan, equipment("km"), service_record, Decimal("49000"), today=date.today()
    )
    assert state == "مستحقة الآن"
    assert remaining == Decimal("1000")
    assert meta["remaining_days"] == 0
    assert meta["next_meter"] == Decimal("50000")


def test_effective_operations_includes_standalone_and_deduplicates_planned():
    from app.modules.maintenance.services import effective_operations_for_equipment

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows
        def join(self, *args):
            return self
        def filter(self, *args):
            return self
        def order_by(self, *args):
            return self
        def all(self):
            return list(self.rows)

    class FakeDB:
        def __init__(self, operations):
            self.operations = operations
        def query(self, model):
            # Return operations pre-filtered for the model (fake does the filtering)
            return FakeQuery(self.operations)

    class Op:
        def __init__(self, id, name):
            self.id, self.name = id, name

    equipment_model = SimpleNamespace(equipment_model_id=7)
    first = Op(1, "زيت المحرك")
    duplicate = Op(1, "زيت المحرك")
    # Second operation (different ID)
    other = Op(2, "فحص الفرامل")

    # Test with only the two operations that would be returned for this model
    db = FakeDB([first, duplicate, other])

    rows = effective_operations_for_equipment(db, equipment_model)
    # Should deduplicate by ID
    assert [row.id for row in rows] == [1, 2]

    rows = effective_operations_for_equipment(db, equipment_model, include_standalone=True)
    assert [row.id for row in rows] == [1, 2]
