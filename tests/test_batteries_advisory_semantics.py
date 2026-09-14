from datetime import date, timedelta

from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.batteries.services import _state_from_history, status


def test_replacement_due_is_not_damage_or_unusable_state():
    battery = Battery(serial_number="B-ADVISORY", expiry_date=date.today() - timedelta(days=1))
    state = {"installed": True}

    # A due/replacement date is an advisory condition, not damage.
    assert status(battery, state, db=None) == "replacement_due"
    assert battery.expiry_date < date.today()


def test_explicit_damage_removal_is_distinct_from_replacement_due():
    battery = Battery(serial_number="B-DAMAGE")
    movement = BatteryMovement(
        id=2,
        battery_id=battery.id,
        movement_date=date.today(),
        movement_type="remove",
        reason="تالف",
    )
    state = {"installed": False, "movement": movement}

    assert status(battery, state, db=None) == "damaged"


def test_history_keeps_latest_install_state_after_normal_removal_and_reinstall():
    movements = [
        BatteryMovement(id=1, battery_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10),
        BatteryMovement(id=2, battery_id=1, movement_date=date(2026, 2, 1), movement_type="remove", reason="صيانة"),
        BatteryMovement(id=3, battery_id=1, movement_date=date(2026, 3, 1), movement_type="install", equipment_id=20),
    ]
    state = _state_from_history(movements)
    assert state["installed"] is True
    assert state["equipment_id"] == 20
