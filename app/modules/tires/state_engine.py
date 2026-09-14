"""Single source of truth for tire movement state semantics."""

from datetime import datetime


REMOVAL_DISPOSITIONS = {"stock", "damaged", "expired"}
DAMAGED_REASONS = {"تالف", "damaged", "تلف"}
EXPIRED_REASONS = {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}


def movement_datetime(movement) -> datetime:
    """Return the required operational timestamp for a tire movement."""
    value = getattr(movement, "movement_datetime", None)
    if value is None:
        raise ValueError("وقت حركة الإطار مطلوب")
    return value


def remove_disposition(movement) -> str:
    explicit = getattr(movement, "removal_disposition", None)
    if explicit in REMOVAL_DISPOSITIONS:
        return explicit
    reason = (getattr(movement, "reason", None) or "").strip().lower()
    if reason in DAMAGED_REASONS:
        return "damaged"
    if reason in EXPIRED_REASONS:
        return "expired"
    return "stock"


def state_from_history(movements):
    """Calculate a tire state from its complete chronological movement history."""
    state = {
        "installed": False,
        "equipment_id": None,
        "position_id": None,
        "equipment": None,
        "position": None,
        "movement": None,
        "disposition": "stock",
    }
    for movement in sorted(movements, key=movement_datetime):
        if movement.movement_type == "remove":
            state = {
                "installed": False,
                "equipment_id": None,
                "position_id": None,
                "equipment": None,
                "position": None,
                "movement": movement,
                "disposition": remove_disposition(movement),
            }
        elif movement.movement_type in {"install", "move"}:
            state = {
                "installed": True,
                "equipment_id": movement.equipment_id,
                "position_id": movement.position_id,
                "equipment": getattr(movement, "equipment", None),
                "position": getattr(movement, "position", None),
                "movement": movement,
                "disposition": "installed",
            }
    return state
