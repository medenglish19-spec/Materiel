from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.tires.models import Tire, TireMovement, TirePosition
from app.modules.tires.services import (
    MOVEMENT_TYPES,
    tire_condition,
    tire_location,
    tire_status,
    validate_movement,
)


def test_tire_models_are_registered_with_expected_tables():
    assert Tire.__tablename__ == "tires"
    assert TireMovement.__tablename__ == "tire_movements"
    assert TirePosition.__tablename__ == "tire_positions"
    assert {"install", "move", "remove"} == MOVEMENT_TYPES


def test_tire_condition_and_location_are_independent():
    tire = Tire(serial_number="T-1", expiry_date=date.today() - timedelta(days=1))
    state = {"installed": True, "disposition": "installed"}

    assert tire_condition(tire, state) == "expired"
    assert tire_location(state) == "installed"
    assert tire_status(tire, state) == "expired"


def test_tire_status_is_derived_from_expiry_and_last_movement():
    tire = Tire(serial_number="T-2", expiry_date=date.today() - timedelta(days=1))
    assert tire_status(tire, None) == "expired"

    tire.expiry_date = date.today() + timedelta(days=30)
    assert tire_status(tire, None) == "unassigned"
    assert tire_status(tire, {"installed": False}) == "stock"
    assert tire_status(tire, {"installed": True}) == "installed"


def test_validate_movement_rejects_installing_expired_tire(db_session):
    tire = Tire(serial_number="T-3", expiry_date=date.today() - timedelta(days=1))
    db_session.add(tire)
    db_session.commit()

    with pytest.raises(ValueError, match="منتهي الصلاحية"):
        validate_movement(
            db_session,
            tire,
            "install",
            date.today(),
            equipment_id=1,
            position_id=1,
            meter_value=Decimal("10"),
        )


def test_validate_movement_rejects_damaged_tire(db_session):
    tire = Tire(serial_number="T-4", expiry_date=date.today() + timedelta(days=30))
    db_session.add(tire)
    db_session.flush()
    db_session.add(
        TireMovement(
            tire_id=tire.id,
            movement_date=date.today(),
            movement_type="remove",
            reason="تالف",
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="تالف"):
        validate_movement(
            db_session,
            tire,
            "install",
            date.today(),
            equipment_id=1,
            position_id=1,
            meter_value=Decimal("10"),
        )
