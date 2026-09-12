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


def save_editor_data(db: Session, model_id: int, payload: dict):
    """Apply all Master Data sections in one transaction and synchronize safe references."""
    model = _get_model(db, model_id)
    _save_properties(db, model_id, payload.get("properties", []))
    _save_tire_items(db, model_id, payload.get("tires", []))
    _save_battery_items(db, model_id, payload.get("batteries", []))
    _save_maintenance(db, model, payload.get("maintenance", []))
    _cleanup_removed_tire_positions(db, model_id)
    sync_model_configuration_fields(db)
    db.commit()
    return _json_safe(get_editor_data(db, model_id))
