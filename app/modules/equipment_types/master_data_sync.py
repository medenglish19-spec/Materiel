from sqlalchemy import text
from sqlalchemy.orm import Session


def sync_model_configuration_fields(db: Session) -> None:
    """Keep legacy/current model fields populated from the new master configurations."""
    db.execute(text("""
        UPDATE equipment_models
        SET has_tires = 1,
            tire_positions_required = COALESCE((
                SELECT COUNT(*)
                FROM master_data_configuration_items i
                WHERE i.configuration_id = equipment_models.tire_configuration_id
            ), 0)
        WHERE tire_configuration_id IS NOT NULL
    """))
    db.execute(text("""
        UPDATE equipment_models
        SET has_batteries = 1,
            battery_count_required = COALESCE((
                SELECT COUNT(*)
                FROM master_data_configuration_items i
                WHERE i.configuration_id = equipment_models.battery_configuration_id
            ), 0)
        WHERE battery_configuration_id IS NOT NULL
    """))


def materialize_tire_positions(db: Session) -> None:
    """Create model-specific TirePosition records from the imported tire configuration.

    Existing records are never deleted. Re-importing the same configuration updates the
    generated record in place, while old records remain available for historical movements.
    """
    models = db.execute(text("""
        SELECT id, tire_configuration_id
        FROM equipment_models
        WHERE tire_configuration_id IS NOT NULL
    """)).all()
    for model_id, config_id in models:
        items = db.execute(text("""
            SELECT item_code, item_name, axle_number, side, position_type, sort_order
            FROM master_data_configuration_items
            WHERE configuration_id=:config_id
            ORDER BY sort_order, id
        """), {"config_id": config_id}).all()
        for item_code, item_name, axle_number, side, position_type, sort_order in items:
            code = f"MD-{model_id}-{item_code}"[:40]
            current = db.execute(text("SELECT id FROM tire_positions WHERE code=:code"), {"code": code}).scalar_one_or_none()
            values = {"code": code, "name": item_name, "description": None, "sort_order": sort_order or 0, "equipment_model_id": model_id, "axle_number": axle_number, "side": side, "position_type": position_type}
            if current is None:
                db.execute(text("""INSERT INTO tire_positions
                    (code,name,description,sort_order,equipment_model_id,axle_number,side,position_type)
                    VALUES (:code,:name,:description,:sort_order,:equipment_model_id,:axle_number,:side,:position_type)"""), values)
            else:
                db.execute(text("""UPDATE tire_positions SET name=:name,description=:description,sort_order=:sort_order,
                    equipment_model_id=:equipment_model_id,axle_number=:axle_number,side=:side,position_type=:position_type
                    WHERE id=:id"""), {**values, "id": current})
