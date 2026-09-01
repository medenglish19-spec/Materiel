from datetime import date, timedelta

from app.modules.tires.models import Tire, TireMovement, TirePosition
from app.modules.tires.services import MOVEMENT_TYPES, tire_status


def test_tire_models_are_registered_with_expected_tables():
    assert Tire.__tablename__ == "tires"
    assert TireMovement.__tablename__ == "tire_movements"
    assert TirePosition.__tablename__ == "tire_positions"
    assert {"install", "move", "remove"} == MOVEMENT_TYPES


def test_tire_status_is_derived_from_expiry_and_last_movement():
    tire = Tire(serial_number="T-1", expiry_date=date.today() - timedelta(days=1))
    assert tire_status(tire, None) == "expired"

    tire.expiry_date = date.today() + timedelta(days=30)
    assert tire_status(tire, None) == "unassigned"
    assert tire_status(tire, {"installed": False}) == "stock"
    assert tire_status(tire, {"installed": True}) == "installed"
