from sqlalchemy.orm import joinedload

from app.modules.tires.models import Tire, TireDisposal, TireMovement


def current_states(db):
    """Load current tire states with batched historical queries.

    The result has the same state shape used by tires.services.current_state,
    while avoiding one movement query per tire in dashboards and list views.
    """
    tires = db.query(Tire).order_by(Tire.serial_number).all()
    movements = (
        db.query(TireMovement)
        .options(joinedload(TireMovement.equipment), joinedload(TireMovement.position))
        .order_by(TireMovement.tire_id.asc(), TireMovement.movement_date.asc(), TireMovement.id.asc())
        .all()
    )
    disposals = db.query(TireDisposal).all()
    disposal_by_tire = {row.tire_id: row for row in disposals}
    grouped = {tire.id: [] for tire in tires}
    for movement in movements:
        if movement.tire_id in grouped:
            grouped[movement.tire_id].append(movement)

    damaged_reasons = {"تالف", "damaged", "تلف"}
    expired_reasons = {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}
    states = {}
    for tire in tires:
        state = None
        for movement in grouped[tire.id]:
            if movement.movement_type == "remove":
                reason = (movement.reason or "").strip().lower()
                if reason in damaged_reasons:
                    disposition = "damaged"
                elif reason in expired_reasons:
                    disposition = "expired"
                else:
                    disposition = "stock"
                state = {
                    "movement": movement,
                    "installed": False,
                    "equipment": None,
                    "position": None,
                    "disposition": disposition,
                }
            else:
                state = {
                    "movement": movement,
                    "installed": True,
                    "equipment": movement.equipment,
                    "position": movement.position,
                    "disposition": "installed",
                }

        disposal = disposal_by_tire.get(tire.id)
        if disposal and (state is None or disposal.disposal_date >= state["movement"].movement_date):
            states[tire.id] = {
                "movement": state["movement"] if state else None,
                "installed": False,
                "equipment": None,
                "position": None,
                "disposition": "disposed",
                "disposal": disposal,
            }
        else:
            states[tire.id] = state
    return tires, states
