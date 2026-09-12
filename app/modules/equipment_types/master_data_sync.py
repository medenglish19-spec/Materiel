from sqlalchemy import text
from sqlalchemy.orm import Session


def sync_model_configuration_fields(db: Session) -> None:
    """Keep legacy/current model fields populated from the new master configurations.

    This is additive: existing columns remain in place so current pages and logic keep working.
    """
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
