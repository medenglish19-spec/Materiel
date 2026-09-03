from datetime import date

from app.modules.tires.models import Tire, TireDisposal, TireMovement
from app.modules.tires.services import (
    _remove_disposition,
    _state_from_history,
    _validate_tire_meter_history,
    tire_status,
)


def test_full_tire_lifecycle_from_install_to_final_disposal():
    tire = Tire(serial_number="LIFE-001", expiry_date=date(2027, 1, 1))

    install = TireMovement(
        id=1,
        tire_id=1,
        movement_date=date(2026, 1, 1),
        movement_type="install",
        equipment_id=10,
        position_id=100,
        meter_value=50000,
    )
    state = _state_from_history([install])
    assert state["installed"] is True
    assert state["equipment_id"] == 10
    assert state["position_id"] == 100
    assert tire_status(tire, {"installed": True, "disposition": "installed"}) == "installed"

    move = TireMovement(
        id=2,
        tire_id=1,
        movement_date=date(2026, 1, 6),
        movement_type="move",
        equipment_id=10,
        position_id=101,
        meter_value=60000,
    )
    state = _state_from_history([install, move])
    assert state["installed"] is True
    assert state["position_id"] == 101

    remove = TireMovement(
        id=3,
        tire_id=1,
        movement_date=date(2026, 1, 9),
        movement_type="remove",
        reason="تالف",
    )
    state = _state_from_history([install, move, remove])
    assert state["installed"] is False
    assert _remove_disposition(remove) == "damaged"
    assert tire_status(tire, {"installed": False, "disposition": "damaged"}) == "damaged"

    disposal = TireDisposal(
        tire_id=1,
        disposal_date=date(2026, 1, 10),
        disposal_document="إخراج-001",
        reason="تالف نهائيًا",
    )
    assert tire_status(
        tire,
        {"installed": False, "disposition": "disposed", "disposal": disposal},
    ) == "disposed"


def test_full_cross_equipment_lifecycle_allows_target_meter_reset():
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
