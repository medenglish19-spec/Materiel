from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.equipment_types.master_data_editor import (
    _get_model,
    _save_properties,
    _save_tire_items,
    _save_battery_items,
    _save_maintenance,
    get_editor_data,
)
from app.modules.equipment_types.master_data_sync import sync_model_configuration_fields


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def get_editor_data_safe(db: Session, model_id: int):
    data = get_editor_data(db, model_id)
    if data["batteries"]["id"]:
        rows = db.execute(text("""
            SELECT item_code, extra_json
            FROM master_data_configuration_items
            WHERE configuration_id=:configuration_id
        """), {"configuration_id": data["batteries"]["id"]}).mappings().all()
        extras = {row["item_code"]: row["extra_json"] for row in rows}
        for item in data["batteries"]["items"]:
            item["extra_json"] = extras.get(item["item_code"])
    return _json_safe(data)


def _cleanup_removed_tire_positions(db: Session, model_id: int) -> None:
    """Remove unused materialized positions after a catalog deletion, never history."""
    prefix = f"MD-{model_id}-"
    rows = db.execute(text("""
        SELECT tp.id, tp.code
        FROM tire_positions tp
        WHERE tp.equipment_model_id=:model_id AND tp.code LIKE :prefix
    """), {"model_id": model_id, "prefix": prefix + "%"}).all()
    for position_id, code in rows:
        item_code = code[len(prefix):]
        exists = db.execute(text("""
            SELECT 1 FROM master_data_configurations c
            JOIN equipment_models m ON m.tire_configuration_id=c.id
            JOIN master_data_configuration_items i ON i.configuration_id=c.id
            WHERE m.id=:model_id AND c.config_type='tire' AND i.item_code=:item_code
            LIMIT 1
        """), {"model_id": model_id, "item_code": item_code}).first()
        if exists:
            continue
        movements = db.execute(text("SELECT COUNT(*) FROM tire_movements WHERE position_id=:position_id"), {"position_id": position_id}).scalar_one()
        if movements:
            continue
        db.execute(text("DELETE FROM tire_positions WHERE id=:id"), {"id": position_id})


def _sync_tire_sizes(db: Session, model_id: int, rows) -> None:
    sizes=[]
    seen=set()
    for row in rows or []:
        size=str(row.get("size") or "").strip()
        if size and size.lower() not in seen:
            seen.add(size.lower()); sizes.append(size)
    if sizes:
        placeholders=",".join(f":s{i}" for i in range(len(sizes)))
        params={f"s{i}": size.lower() for i,size in enumerate(sizes)}
        params["model_id"]=model_id
        db.execute(text(f"DELETE FROM tire_model_sizes WHERE equipment_model_id=:model_id AND lower(size) NOT IN ({placeholders})"), params)
    else:
        db.execute(text("DELETE FROM tire_model_sizes WHERE equipment_model_id=:model_id"), {"model_id": model_id})
    existing={str(x[0]).strip().lower() for x in db.execute(text("SELECT size FROM tire_model_sizes WHERE equipment_model_id=:model_id"), {"model_id": model_id}).all()}
    for size in sizes:
        if size.lower() not in existing:
            db.execute(text("INSERT INTO tire_model_sizes (equipment_model_id,size) VALUES (:model_id,:size)"), {"model_id": model_id,"size":size})
    db.execute(text("""
        UPDATE equipment_models SET tire_size=(
            SELECT size FROM tire_model_sizes WHERE equipment_model_id=:model_id ORDER BY id LIMIT 1
        ) WHERE id=:model_id
    """), {"model_id": model_id})


def _sync_model_counts_and_defaults(db: Session, model_id: int) -> None:
    db.execute(text("""
        UPDATE equipment_models SET
            has_tires=CASE WHEN EXISTS (
                SELECT 1 FROM master_data_configuration_items i
                WHERE i.configuration_id=equipment_models.tire_configuration_id
            ) THEN 1 ELSE 0 END,
            tire_positions_required=COALESCE((SELECT COUNT(*) FROM master_data_configuration_items i WHERE i.configuration_id=equipment_models.tire_configuration_id),0),
            has_batteries=CASE WHEN EXISTS (
                SELECT 1 FROM master_data_configuration_items i
                WHERE i.configuration_id=equipment_models.battery_configuration_id
            ) THEN 1 ELSE 0 END,
            battery_count_required=COALESCE((SELECT SUM(COALESCE(CAST(json_extract(i.extra_json,'$.count') AS INTEGER),0)) FROM master_data_configuration_items i WHERE i.configuration_id=equipment_models.battery_configuration_id),0),
            battery_capacity_ah=(SELECT value_number FROM master_data_configuration_items i WHERE i.configuration_id=equipment_models.battery_configuration_id ORDER BY i.sort_order,i.id LIMIT 1),
            battery_voltage_v=CAST((SELECT json_extract(i.extra_json,'$.voltage') FROM master_data_configuration_items i WHERE i.configuration_id=equipment_models.battery_configuration_id ORDER BY i.sort_order,i.id LIMIT 1) AS FLOAT)
        WHERE id=:model_id
    """), {"model_id": model_id})


def save_editor_data(db: Session, model_id: int, payload: dict):
    """Apply all Master Data sections in one transaction and synchronize safe references."""
    model = _get_model(db, model_id)
    properties=payload.get("properties",[])
    tires=payload.get("tires",[])
    batteries=payload.get("batteries",[])
    maintenance=payload.get("maintenance",[])
    _save_properties(db, model_id, properties)
    _save_tire_items(db, model_id, tires)
    _sync_tire_sizes(db, model_id, tires)
    _save_battery_items(db, model_id, batteries)
    _save_maintenance(db, model, maintenance)
    _cleanup_removed_tire_positions(db, model_id)
    sync_model_configuration_fields(db)
    _sync_model_counts_and_defaults(db, model_id)
    db.commit()
    return get_editor_data_safe(db, model_id)
