import pytest

from app.modules.batteries.models import BatteryMovement, _validate_battery_movement_policy
from app.modules.tires.models import TireMovement, _validate_tire_movement_policy


@pytest.mark.parametrize(
    "movement_cls, validator, label",
    [
        (BatteryMovement, _validate_battery_movement_policy, "البطارية"),
        (TireMovement, _validate_tire_movement_policy, "الإطار"),
    ],
)
def test_direct_move_is_rejected_at_model_boundary(movement_cls, validator, label):
    with pytest.raises(ValueError, match=f"نقل {label} المباشر غير مسموح"):
        validator(None, None, movement_cls(movement_type="move"))


@pytest.mark.parametrize(
    "movement_cls, validator, label",
    [
        (BatteryMovement, _validate_battery_movement_policy, "البطارية"),
        (TireMovement, _validate_tire_movement_policy, "الإطار"),
    ],
)
def test_remove_requires_reason_at_model_boundary(movement_cls, validator, label):
    with pytest.raises(ValueError, match=f"سبب فك {label} إلزامي"):
        validator(None, None, movement_cls(movement_type="remove", reason=""))


@pytest.mark.parametrize(
    "movement_cls, validator",
    [(BatteryMovement, _validate_battery_movement_policy), (TireMovement, _validate_tire_movement_policy)],
)
def test_remove_with_reason_is_allowed(movement_cls, validator):
    movement = movement_cls(movement_type="remove", reason="استبدال")
    validator(None, None, movement)
