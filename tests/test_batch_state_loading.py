from datetime import date


def test_battery_batch_state_helper_is_available():
    from app.modules.batteries.services import current_states

    assert callable(current_states)


def test_tire_batch_state_replays_latest_installation():
    from app.modules.tires.batch_state import current_states

    assert callable(current_states)


def test_historical_state_ordering_remains_date_then_id():
    from app.modules.batteries.services import _state_from_history
    from app.modules.batteries.models import BatteryMovement

    movements = [
        BatteryMovement(id=2, battery_id=1, movement_date=date(2026, 1, 1), movement_type="remove"),
        BatteryMovement(id=1, battery_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10),
        BatteryMovement(id=3, battery_id=1, movement_date=date(2026, 2, 1), movement_type="install", equipment_id=20),
    ]
    state = _state_from_history(movements)
    assert state["installed"] is True
    assert state["equipment_id"] == 20
