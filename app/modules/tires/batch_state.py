from datetime import date, datetime, time

from sqlalchemy.orm import joinedload

from app.modules.equipment.models import Equipment
from app.modules.tires.models import Tire, TireDisposal, TireMovement


def _movement_datetime(movement):
    value = getattr(movement, "movement_datetime", None)
    return value if value is not None else datetime.combine(movement.movement_date, time.min)


def _remove_disposition(movement):
    explicit = getattr(movement, "removal_disposition", None)
    if explicit in {"stock", "damaged", "expired"}:
        return explicit
    reason = (movement.reason or "").strip().lower()
    if reason in {"تالف", "damaged", "تلف"}:
        return "damaged"
    if reason in {"انتهاء الصلاحية", "منتهي الصلاحية", "expired"}:
        return "expired"
    return "stock"


def current_states(db):
    tires = db.query(Tire).order_by(Tire.serial_number).all()
    movements = db.query(TireMovement).options(joinedload(TireMovement.equipment), joinedload(TireMovement.position)).all()
    movements.sort(key=lambda m: (m.tire_id, _movement_datetime(m), m.id))
    disposals = db.query(TireDisposal).all()
    disposal_by_tire = {row.tire_id: row for row in disposals}
    grouped = {tire.id: [] for tire in tires}
    for movement in movements:
        if movement.tire_id in grouped:
            grouped[movement.tire_id].append(movement)

    states = {}
    for tire in tires:
        state = None
        for movement in grouped[tire.id]:
            if movement.movement_type == "remove":
                state = {"movement": movement, "installed": False, "equipment": None, "position": None, "disposition": _remove_disposition(movement)}
            else:
                state = {"movement": movement, "installed": True, "equipment": movement.equipment, "position": movement.position, "disposition": "installed"}
        disposal = disposal_by_tire.get(tire.id)
        if disposal and (state is None or disposal.disposal_date >= _movement_datetime(state["movement"]).date()):
            states[tire.id] = {"movement": state["movement"] if state else None, "installed": False, "equipment": None, "position": None, "disposition": "disposed", "disposal": disposal}
        else:
            states[tire.id] = state
    return tires, states


def _status(tire, state):
    if state and state.get("disposition") == "disposed":
        return "disposed"
    if state and state.get("disposition") in {"damaged", "expired"}:
        return state["disposition"]
    if tire.expiry_date and tire.expiry_date < date.today():
        return "expired"
    if state and state.get("installed"):
        return "installed"
    return "stock" if state else "unassigned"


def dashboard_stats_from_snapshot(tires, states):
    counts = {"total": len(tires), "installed": 0, "stock": 0, "expired": 0, "damaged": 0, "disposed": 0, "unassigned": 0}
    for tire in tires:
        status = _status(tire, states.get(tire.id))
        counts[status] = counts.get(status, 0) + 1
    return counts


def dashboard_stats(db):
    tires, states = current_states(db)
    return dashboard_stats_from_snapshot(tires, states)


def inventory(db):
    tires, states = current_states(db)
    from app.modules.tires import services
    result = []
    for tire in tires:
        state = states.get(tire.id)
        if state and state.get("disposition") == "disposed":
            continue
        if not state or not state.get("installed"):
            result.append({"tire": tire, "state": state, "status": services.tire_status(tire, state), "condition": services.tire_condition(tire, state), "location": services.tire_location(state)})
    return result


def _installed_for_equipment_from_snapshot(tires, states, equipment_id):
    from app.modules.tires import services
    rows = []
    for tire in tires:
        state = states.get(tire.id)
        equipment = state.get("equipment") if state else None
        if state and state.get("installed") and equipment and equipment.id == equipment_id:
            rows.append({"tire": tire, "state": state, "condition": services.tire_condition(tire, state), "location": services.tire_location(state)})
    return sorted(rows, key=lambda x: (x["state"]["position"].sort_order if x["state"]["position"] else 9999, x["state"]["position"].id if x["state"]["position"] else 9999))


def installed_for_equipment(db, equipment_id):
    tires, states = current_states(db)
    return _installed_for_equipment_from_snapshot(tires, states, equipment_id)


def equipment_position_view_from_snapshot(db, equipment, tires, states):
    from app.modules.tires import services
    configured = services.list_positions(db, equipment.equipment_model_id)
    mounted = {item["state"]["position"].id: item for item in _installed_for_equipment_from_snapshot(tires, states, equipment.id) if item["state"].get("position")}
    result = [{"position": position, "item": mounted.get(position.id)} for position in configured]
    configured_ids = {position.id for position in configured}
    for item in mounted.values():
        position = item["state"]["position"]
        if position.id not in configured_ids:
            result.append({"position": position, "item": item})
    return sorted(result, key=lambda x: (x["position"].axle_number or 9999, x["position"].sort_order, x["position"].id))


def equipment_position_view(db, equipment_id):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        return []
    tires, states = current_states(db)
    return equipment_position_view_from_snapshot(db, equipment, tires, states)
