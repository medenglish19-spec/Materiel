from datetime import date, timedelta

from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.batteries.services import MOVEMENT_TYPES, status


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
