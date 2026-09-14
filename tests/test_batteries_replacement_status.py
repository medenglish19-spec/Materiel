from datetime import date, timedelta

from app.modules.batteries.models import Battery
from app.modules.batteries.services import status


def test_due_battery_is_not_reported_as_expired_unusable():
    battery = Battery(serial_number="B-DUE", expiry_date=date.today() - timedelta(days=1))
    state = {"installed": True}

    assert status(battery, state, db=None) == "replacement_due"


def test_due_battery_can_remain_in_stock():
    battery = Battery(serial_number="B-STOCK-DUE", expiry_date=date.today() - timedelta(days=1))
    state = {"installed": False}

    assert status(battery, state, db=None) == "stock"
