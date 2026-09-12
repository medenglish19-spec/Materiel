from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.modules.equipment.models import Equipment
from app.modules.tires.models import Tire, TireModelSize, TireMovement, TirePosition
from app.modules.tires.services import _state_from_history, _validate_model_position


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value if isinstance(self.value, list) else []


class _DB:
    def __init__(self, equipment, position, sizes):
        self.equipment = equipment
        self.position = position
        self.sizes = sizes

    def query(self, model):
        if model is Equipment:
            return _Query(self.equipment)
        if model is TirePosition:
            return _Query(self.position)
        if model is TireModelSize:
            return _Query(self.sizes)
        raise AssertionError(f"Unexpected query model: {model}")


def _equipment(model):
    return SimpleNamespace(
        id=1,
        equipment_model_id=7,
        equipment_model=model,
        registration_number="A-001",
        asset_code=None,
    )


def _position():
    return SimpleNamespace(id=10, equipment_model_id=7, name="أمام يسار")


def test_install_is_blocked_when_master_data_has_no_approved_tire_size():
    model = SimpleNamespace(tire_size=None)
    db = _DB(_equipment(model), _position(), [])
    tire = Tire(serial_number="SIZE-001", size="315/80R22.5", expiry_date=date.today() + timedelta(days=30))

    with pytest.raises(ValueError, match="لم يتم تحديد أي مقاس إطار معتمد لهذا الطراز في Master Data"):
        _validate_model_position(db, 1, 10, tire)


def test_model_default_tire_size_is_used_when_no_explicit_size_rows_exist():
    model = SimpleNamespace(tire_size="315/80R22.5")
    db = _DB(_equipment(model), _position(), [])

    accepted = Tire(serial_number="SIZE-002", size="315/80R22.5")
    _validate_model_position(db, 1, 10, accepted)

    rejected = Tire(serial_number="SIZE-003", size="295/80R22.5")
    with pytest.raises(ValueError, match="غير مطابق للمقاس المعتمد"):
        _validate_model_position(db, 1, 10, rejected)


def test_explicit_tire_model_sizes_override_model_default_size():
    model = SimpleNamespace(tire_size="315/80R22.5")
    sizes = [TireModelSize(id=1, equipment_model_id=7, size="295/80R22.5")]
    db = _DB(_equipment(model), _position(), sizes)

    accepted = Tire(serial_number="SIZE-004", size="295/80R22.5")
    _validate_model_position(db, 1, 10, accepted)

    rejected = Tire(serial_number="SIZE-005", size="315/80R22.5")
    with pytest.raises(ValueError, match="غير معتمد لهذا الطراز"):
        _validate_model_position(db, 1, 10, rejected)


def test_historical_state_is_independent_of_later_current_state():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, position_id=100),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 2, 1), movement_type="remove", reason="تالف"),
        TireMovement(id=3, tire_id=1, movement_date=date(2026, 3, 1), movement_type="install", equipment_id=20, position_id=200),
    ]

    current = _state_from_history(movements)
    january = _state_from_history([m for m in movements if m.movement_date <= date(2026, 1, 15)])
    february = _state_from_history([m for m in movements if m.movement_date <= date(2026, 2, 15)])

    assert current["installed"] is True
    assert current["equipment_id"] == 20
    assert january["installed"] is True
    assert january["equipment_id"] == 10
    assert february["installed"] is False
    assert february["disposition"] == "damaged"
