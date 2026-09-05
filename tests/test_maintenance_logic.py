from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.maintenance.models import _validate_record


class _Result:
    def __init__(self, scalar=None, first=None, rows=None):
        self._scalar = scalar
        self._first = first
        self._rows = rows or []

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
