from sqlalchemy import text
from sqlalchemy.orm import Session


def sync_model_configuration_fields(db: Session) -> None:
    """Synchronize catalog-level model counts and materialize fixed tire positions."""
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
    materialize_tire_positions(db)


def materialize_tire_positions(db: Session) -> None:
    """Materialize fixed tire-position references without changing historical meanings.

    Master Data describes only the fixed layout of a model (axle/side/position).
    It never contains the identity of the tire installed in a position.

    A position referenced by historical tire movements is immutable. If its catalog
    definition changes, the import is rejected so the caller can introduce a new
    configuration/position definition instead of rewriting history.
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
            current = db.execute(text("""
                SELECT id, name, axle_number, side, position_type, sort_order
                FROM tire_positions
                WHERE code=:code
            """), {"code": code}).one_or_none()
            values = {
                "code": code,
                "name": item_name,
                "description": None,
                "sort_order": sort_order or 0,
                "equipment_model_id": model_id,
                "axle_number": axle_number,
                "side": side,
                "position_type": position_type,
            }
            if current is None:
                db.execute(text("""
                    INSERT INTO tire_positions
                    (code,name,description,sort_order,equipment_model_id,axle_number,side,position_type)
                    VALUES (:code,:name,:description,:sort_order,:equipment_model_id,:axle_number,:side,:position_type)
                """), values)
                continue

            changed = tuple(current[1:]) != (
                item_name,
                axle_number,
                side,
                position_type,
                sort_order or 0,
            )
            if not changed:
                continue

            movement_count = db.execute(text("""
                SELECT COUNT(*)
                FROM tire_movements
                WHERE position_id=:position_id
            """), {"position_id": current[0]}).scalar_one()
            if movement_count:
                raise ValueError(
                    f"موضع الإطار {code} مرتبط بـ {movement_count} حركة تاريخية؛ "
                    "لا يمكن تغيير تعريفه في مكانه. أنشئ Configuration/Position جديدًا "
                    "للتعريف الجديد حتى تبقى الحركات السابقة كما هي."
                )

            db.execute(text("""
                UPDATE tire_positions
                SET name=:name,
                    description=:description,
                    sort_order=:sort_order,
                    equipment_model_id=:equipment_model_id,
                    axle_number=:axle_number,
                    side=:side,
                    position_type=:position_type
                WHERE id=:id
            """), {**values, "id": current[0]})
