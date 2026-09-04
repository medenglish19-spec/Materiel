from datetime import date
from decimal import Decimal

from app.modules.tires.models import Tire, TireDisposal, TireMovement
from app.modules.tires.services import _remove_disposition, _state_from_history, _validate_tire_meter_history, tire_status


def test_full_tire_lifecycle_from_install_to_final_disposal():
    tire = Tire(serial_number="LIFE-001", expiry_date=date(2027, 1, 1))
    install = TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, position_id=100, meter_value=50000)
    move = TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 6), movement_type="move", equipment_id=10, position_id=101, meter_value=60000)
    remove = TireMovement(id=3, tire_id=1, movement_date=date(2026, 1, 9), movement_type="remove", reason="تالف")

    state = _state_from_history([install, move])
    assert state["installed"] is True
    assert state["position_id"] == 101
    assert tire_status(tire, {"installed": True, "disposition": "installed"}) == "installed"

    state = _state_from_history([install, move, remove])
    assert state["installed"] is False
    assert _remove_disposition(remove) == "damaged"
    assert tire_status(tire, {"installed": False, "disposition": "damaged"}) == "damaged"

    disposal = TireDisposal(tire_id=1, disposal_date=date(2026, 1, 10), disposal_document="إخراج-001", reason="تالف نهائيًا")
    assert tire_status(tire, {"installed": False, "disposition": "disposed", "disposal": disposal}) == "disposed"


def test_cross_equipment_lifecycle_allows_target_meter_reset():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, meter_value=120000),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 10), movement_type="move", equipment_id=10, meter_value=125000),
        TireMovement(id=3, tire_id=1, movement_date=date(2026, 1, 11), movement_type="move", equipment_id=20, meter_value=35000),
        TireMovement(id=4, tire_id=1, movement_date=date(2026, 1, 20), movement_type="move", equipment_id=20, meter_value=42000),
        TireMovement(id=5, tire_id=1, movement_date=date(2026, 1, 25), movement_type="remove", reason="تالف"),
    ]
    _validate_tire_meter_history(movements)
    assert _remove_disposition(movements[-1]) == "damaged"
    assert _state_from_history(movements)["installed"] is False


def test_meter_history_rejects_backward_reading_on_same_equipment():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, meter_value=50000),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 2), movement_type="move", equipment_id=10, meter_value=49000),
    ]
    try:
        _validate_tire_meter_history(movements)
    except ValueError as exc:
        assert "عداد" in str(exc)
    else:
        raise AssertionError("Expected backward meter history to be rejected")


def test_meter_history_allows_equal_reading_when_no_usage_was_recorded():
    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, meter_value=Decimal("50000")),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 2), movement_type="move", equipment_id=10, meter_value=Decimal("50000")),
    ]
    _validate_tire_meter_history(movements)
