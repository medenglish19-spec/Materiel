import pytest

from app.modules.batteries.models import BatteryMovement
from app.modules.tires.models import TireMovement


@pytest.mark.parametrize(
    "movement_cls, label",
    [(BatteryMovement, "البطارية"), (TireMovement, "الإطار")],
)
def test_direct_move_is_rejected_by_models(movement_cls, label):
    with pytest.raises(ValueError, match=f"نقل {label} المباشر غير مسموح"):
        movement_cls(movement_type="move")


@pytest.mark.parametrize(
    "movement_cls, label",
    [(BatteryMovement, "البطارية"), (TireMovement, "الإطار")],
)
def test_remove_requires_reason_at_model_boundary(movement_cls, label):
    with pytest.raises(ValueError, match=f"سبب فك {label} إلزامي"):
        movement_cls(movement_type="remove", reason="")


@pytest.mark.parametrize("movement_cls", [BatteryMovement, TireMovement])
def test_remove_with_reason_is_allowed(movement_cls):
    movement = movement_cls(movement_type="remove", reason="استبدال")
    assert movement.reason == "استبدال"
