from datetime import date, timedelta
from types import SimpleNamespace
from decimal import Decimal

import pytest

from app.modules.maintenance.router import status_for, priority_for
from app.modules.maintenance.models import _validate_record


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


class _Result:
    def __init__(self, rows=None, scalar=None, first=None):
        self._rows = rows or []
        self._scalar = scalar
        self._first = first

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _MaintenanceValidationConnection:
    def __init__(self, same_day_rows):
        self.same_day_rows = same_day_rows
        self.calls = 0

    def execute(self, statement):
        self.calls += 1
        if self.calls == 1:
            return _Result(scalar="km")
        if self.calls == 2:
            return _Result(first=(20,))
        if self.calls == 3:
            return _Result(first=(20,))
        if self.calls == 4:
            return _Result(rows=self.same_day_rows)
        return _Result(rows=[])


def _validation_target(meter, record_id=None):
    return SimpleNamespace(
        equipment_id=20,
        rule_id=10,
        maintenance_date=date(2026, 9, 5),
        meter_value=Decimal(str(meter)),
        id=record_id,
    )


def test_same_day_new_maintenance_cannot_go_backwards_in_meter():
    connection = _MaintenanceValidationConnection([(date(2026, 9, 5), Decimal("100"), 1)])
    with pytest.raises(ValueError, match="في نفس يوم الصيانة"):
        _validate_record(connection, _validation_target(90))


def test_same_day_new_maintenance_can_keep_or_increase_meter():
    connection = _MaintenanceValidationConnection([(date(2026, 9, 5), Decimal("100"), 1)])
    _validate_record(connection, _validation_target(100))
    connection = _MaintenanceValidationConnection([(date(2026, 9, 5), Decimal("100"), 1)])
    _validate_record(connection, _validation_target(110))


def test_same_day_update_respects_record_id_order():
    connection = _MaintenanceValidationConnection([(date(2026, 9, 5), Decimal("100"), 1)])
    with pytest.raises(ValueError, match="في نفس يوم الصيانة"):
        _validate_record(connection, _validation_target(90, record_id=2), exclude_id=2)

    connection = _MaintenanceValidationConnection([(date(2026, 9, 5), Decimal("100"), 2)])
    _validate_record(connection, _validation_target(90, record_id=1), exclude_id=1)
