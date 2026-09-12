from datetime import date
from types import SimpleNamespace

import pytest

from app.modules.tires import services


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _DB:
    def __init__(self, equipment):
        self.equipment = equipment

    def query(self, model):
        return _Query(self.equipment)


def _equipment(required):
    model = SimpleNamespace(tire_positions_required=required)
    return SimpleNamespace(equipment_model=model)


def test_model_capacity_allows_install_below_required(monkeypatch):
    db = _DB(_equipment(4))
    monkeypatch.setattr(services, "_installed_tire_count", lambda db, equipment_id, exclude_tire_id=None: 3)
    services._validate_model_capacity(db, 1, 99, "install")


def test_model_capacity_blocks_install_at_required(monkeypatch):
    db = _DB(_equipment(4))
    monkeypatch.setattr(services, "_installed_tire_count", lambda db, equipment_id, exclude_tire_id=None: 4)
    with pytest.raises(ValueError, match="4"):
        services._validate_model_capacity(db, 1, 99, "install")


def test_model_capacity_self_exclusion_allows_same_equipment_move(monkeypatch):
    db = _DB(_equipment(4))
    captured = {}

    def fake_count(db, equipment_id, exclude_tire_id=None, when=None):
        captured["exclude"] = exclude_tire_id
        captured["when"] = when
        return 3

    monkeypatch.setattr(services, "_installed_tire_count", fake_count)
    when = date(2026, 1, 10)
    services._validate_model_capacity(db, 1, 42, "move", when)
    assert captured == {"exclude": 42, "when": when}


def test_model_capacity_uses_state_at_movement_date(monkeypatch):
    equipment = _equipment(4)
    tires = [SimpleNamespace(id=i) for i in range(1, 6)]
    db = SimpleNamespace()

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return equipment

        def all(self):
            return tires

    db.query = lambda model: Query()
    calls = []

    def fake_state_at(db, tire_id, when, extra=None):
        calls.append((tire_id, when))
        return {"installed": tire_id in {1, 2, 3}, "equipment_id": 1, "position_id": tire_id}

    monkeypatch.setattr(services, "_tire_state_at", fake_state_at)
    when = date(2025, 1, 1)
    services._validate_model_capacity(db, 1, 99, "install", when)
    assert calls
    assert all(call_date == when for _, call_date in calls)


def test_model_capacity_is_disabled_when_no_required_count(monkeypatch):
    db = _DB(_equipment(0))
    called = {"count": False}

    def fake_count(*args, **kwargs):
        called["count"] = True
        return 999

    monkeypatch.setattr(services, "_installed_tire_count", fake_count)
    services._validate_model_capacity(db, 1, 99, "install")
    assert called["count"] is False
