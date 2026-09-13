from datetime import date

from app.modules.tires import batch_state
from app.modules.tires.models import Tire


class FakePosition:
    def __init__(self, position_id, sort_order=1, axle_number=1):
        self.id = position_id
        self.sort_order = sort_order
        self.axle_number = axle_number


class FakeEquipment:
    def __init__(self, equipment_id):
        self.id = equipment_id


class FakeMovement:
    def __init__(self, equipment_id=None, position=None):
        self.equipment = FakeEquipment(equipment_id) if equipment_id is not None else None
        self.position = position


def _snapshot():
    tires = [
        Tire(id=1, serial_number="T-001", expiry_date=date(2099, 1, 1)),
        Tire(id=2, serial_number="T-002", expiry_date=date(2099, 1, 1)),
        Tire(id=3, serial_number="T-003", expiry_date=date(2000, 1, 1)),
    ]
    p1 = FakePosition(11, sort_order=1, axle_number=1)
    p2 = FakePosition(12, sort_order=2, axle_number=1)
    states = {
        1: {
            "installed": True,
            "equipment": FakeEquipment(7),
            "position": p2,
            "disposition": "installed",
        },
        2: {
            "installed": False,
            "equipment": None,
            "position": None,
            "disposition": "stock",
        },
        3: {
            "installed": False,
            "equipment": None,
            "position": None,
            "disposition": "stock",
        },
    }
    return tires, states, p1, p2


def test_dashboard_stats_uses_one_batched_snapshot(monkeypatch):
    tires, states, _, _ = _snapshot()
    calls = []

    def snapshot(db):
        calls.append(db)
        return tires, states

    monkeypatch.setattr(batch_state, "current_states", snapshot)

    counts = batch_state.dashboard_stats(object())

    assert len(calls) == 1
    assert counts == {
        "total": 3,
        "installed": 1,
        "stock": 1,
        "expired": 1,
        "damaged": 0,
        "disposed": 0,
        "unassigned": 0,
    }


def test_inventory_uses_one_batched_snapshot(monkeypatch):
    tires, states, _, _ = _snapshot()
    calls = []

    monkeypatch.setattr(
        batch_state,
        "current_states",
        lambda db: (calls.append(db) or (tires, states)),
    )

    rows = batch_state.inventory(object())

    assert len(calls) == 1
    assert [row["tire"].serial_number for row in rows] == ["T-002", "T-003"]
    assert rows[0]["location"] == "stock"
    assert rows[1]["status"] == "expired"


def test_installed_for_equipment_uses_one_batched_snapshot(monkeypatch):
    tires, states, _, p2 = _snapshot()
    calls = []

    monkeypatch.setattr(
        batch_state,
        "current_states",
        lambda db: (calls.append(db) or (tires, states)),
    )

    rows = batch_state.installed_for_equipment(object(), 7)

    assert len(calls) == 1
    assert len(rows) == 1
    assert rows[0]["tire"].serial_number == "T-001"
    assert rows[0]["state"]["position"] is p2
