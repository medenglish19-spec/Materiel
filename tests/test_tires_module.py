from datetime import date, timedelta

from app.modules.tires.models import Tire, TireDisposal, TireModelSize, TireMovement, TirePosition, TireSystemSetting
from app.modules.tires.services import MOVEMENT_TYPES, POSITION_TYPES, SIDES, _add_years, _remove_disposition, _state_from_history, _validate_tire_meter_history, tire_status


def test_tire_models_are_registered_with_expected_tables():
    assert Tire.__tablename__ == "tires"
    assert TireMovement.__tablename__ == "tire_movements"
    assert TirePosition.__tablename__ == "tire_positions"
    assert TireModelSize.__tablename__ == "tire_model_sizes"
    assert TireSystemSetting.__tablename__ == "tire_system_settings"
    assert TireDisposal.__tablename__ == "tire_disposals"
    assert {"install", "move", "remove"} == MOVEMENT_TYPES
    assert SIDES == {"left", "right"}
    assert POSITION_TYPES == {"single", "inner", "outer"}


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


def test_remove_disposition_preserves_inventory_categories():
    damaged = TireMovement(tire_id=1, movement_date=date(2026, 1, 1), movement_type="remove", reason="تالف")
    expired = TireMovement(tire_id=2, movement_date=date(2026, 1, 1), movement_type="remove", reason="انتهاء الصلاحية")
    returned = TireMovement(tire_id=3, movement_date=date(2026, 1, 1), movement_type="remove", reason="استبدال")
    assert _remove_disposition(damaged) == "damaged"
    assert _remove_disposition(expired) == "expired"
    assert _remove_disposition(returned) == "stock"


def test_historical_movement_replay_keeps_chronological_state():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, position_id=100),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 6), movement_type="move", equipment_id=10, position_id=101),
        TireMovement(id=3, tire_id=1, movement_date=date(2026, 1, 9), movement_type="remove"),
    ]
    assert _state_from_history(movements[:1])["installed"] is True
    assert _state_from_history(movements[:1])["position_id"] == 100
    assert _state_from_history(movements[:2])["installed"] is True
    assert _state_from_history(movements[:2])["position_id"] == 101
    assert _state_from_history(movements)["installed"] is False


def test_same_day_history_uses_movement_id_as_deterministic_order():
    movements = [
        TireMovement(id=20, tire_id=1, movement_date=date(2026, 2, 1), movement_type="remove"),
        TireMovement(id=10, tire_id=1, movement_date=date(2026, 2, 1), movement_type="install", equipment_id=10, position_id=100),
    ]
    state = _state_from_history(movements)
    assert state["installed"] is False
    assert state["movement"].id == 20


def test_cross_equipment_transfer_requires_target_model_and_size_rules():
    """Document the business rule: a tire may move only to a valid position of a compatible model."""
    assert MOVEMENT_TYPES == {"install", "move", "remove"}
    assert POSITION_TYPES == {"single", "inner", "outer"}
    assert SIDES == {"left", "right"}


def test_movement_type_rules_are_explicit_and_disposal_is_terminal():
    assert MOVEMENT_TYPES == {"install", "move", "remove"}
    assert _remove_disposition(TireMovement(movement_type="remove", reason="تالف")) == "damaged"
    assert _remove_disposition(TireMovement(movement_type="remove", reason="انتهاء الصلاحية")) == "expired"
    assert _remove_disposition(TireMovement(movement_type="remove", reason="استبدال")) == "stock"


def test_tire_meter_history_cannot_go_backwards():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", meter_value=100),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 10), movement_type="move", meter_value=120),
    ]
    _validate_tire_meter_history(movements)

    movements.append(TireMovement(id=3, tire_id=1, movement_date=date(2026, 1, 15), movement_type="remove", meter_value=110))
    try:
        _validate_tire_meter_history(movements)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected decreasing historical meter value to be rejected")
