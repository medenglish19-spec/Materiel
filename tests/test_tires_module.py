from datetime import date, timedelta

from app.modules.tires.models import Tire, TireDisposal, TireModelSize, TireMovement, TirePosition, TireSystemSetting
from app.modules.tires.services import MOVEMENT_TYPES, tire_status, _add_years


def test_tire_models_are_registered_with_expected_tables():
    assert Tire.__tablename__ == "tires"
    assert TireMovement.__tablename__ == "tire_movements"
    assert TirePosition.__tablename__ == "tire_positions"
    assert TireModelSize.__tablename__ == "tire_model_sizes"
    assert TireSystemSetting.__tablename__ == "tire_system_settings"
    assert TireDisposal.__tablename__ == "tire_disposals"
    assert {"install", "move", "remove"} == MOVEMENT_TYPES


def test_tire_status_is_derived_from_expiry_and_last_movement():
    tire = Tire(serial_number="T-1", expiry_date=date.today() - timedelta(days=1))
    assert tire_status(tire, None) == "expired"

    tire.expiry_date = date.today() + timedelta(days=30)
    assert tire_status(tire, None) == "unassigned"
    assert tire_status(tire, {"installed": False, "disposition": "stock"}) == "stock"
    assert tire_status(tire, {"installed": False, "disposition": "damaged"}) == "damaged"
    assert tire_status(tire, {"installed": True, "disposition": "installed"}) == "installed"
    assert tire_status(tire, {"installed": False, "disposition": "disposed"}) == "disposed"


def test_validity_years_is_not_hardcoded_to_three():
    assert _add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert _add_years(date(2024, 1, 15), 5) == date(2029, 1, 15)
