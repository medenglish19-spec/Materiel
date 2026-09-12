from datetime import date, timedelta

from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.batteries.services import MOVEMENT_TYPES, _equipment_age_below_limit, _state_from_history, status
from app.modules.equipment.models import Equipment


def test_battery_models_and_movement_types():
    assert Battery.__tablename__ == "batteries"
    assert BatteryMovement.__tablename__ == "battery_movements"
    assert MOVEMENT_TYPES == {"install", "move", "remove"}


def test_battery_status_is_derived():
    battery = Battery(serial_number="B-1", expiry_date=date.today() - timedelta(days=1))
    assert status(battery, None) == "expired"
    battery.expiry_date = date.today() + timedelta(days=30)
    assert status(battery, None) == "unassigned"
    assert status(battery, {"installed": False}) == "stock"
    assert status(battery, {"installed": True}) == "installed"


def test_battery_state_is_replayed_from_history_not_current_state():
    movements = [
        BatteryMovement(id=1, battery_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10),
        BatteryMovement(id=2, battery_id=1, movement_date=date(2026, 2, 1), movement_type="remove"),
        BatteryMovement(id=3, battery_id=1, movement_date=date(2026, 3, 1), movement_type="install", equipment_id=20),
    ]
    state = _state_from_history(movements)
    assert state["installed"] is True
    assert state["equipment_id"] == 20

    historical_state = _state_from_history([m for m in movements if m.movement_date <= date(2026, 2, 15)])
    assert historical_state["installed"] is False
    assert historical_state["equipment_id"] is None


def test_new_equipment_age_exception_uses_first_service_date():
    equipment = Equipment(first_service_date=date(2021, 1, 1))
    assert _equipment_age_below_limit(equipment, date(2026, 1, 1), 6) is True
    assert _equipment_age_below_limit(equipment, date(2027, 1, 1), 6) is False


def test_damage_is_not_inferred_from_age_or_expiry():
    battery = Battery(serial_number="B-2", expiry_date=date.today() - timedelta(days=1))
    assert status(battery, {"installed": True}, equipment=None, db=None) == "expired"
    movement = BatteryMovement(id=9, battery_id=2, movement_date=date.today(), movement_type="remove", reason="تالف")
    assert status(battery, {"installed": False, "movement": movement}, equipment=None, db=None) == "damaged"
