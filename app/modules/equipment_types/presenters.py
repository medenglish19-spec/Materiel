from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.equipment_types.models import EquipmentModel
from app.modules.tires.models import TireModelSize, TirePosition


def model_editor_payload(db: Session, model: EquipmentModel) -> dict:
    """Return the complete model-editor state using JSON-safe primitives only."""
    equipment_type = model.equipment_type
    return {
        "id": model.id,
        "name": model.name,
        "category_id": equipment_type.category_id if equipment_type else None,
        "technical_library_category_id": equipment_type.technical_library_category_id if equipment_type else None,
        "equipment_type_id": model.equipment_type_id,
        "brand_id": model.brand_id,
        "has_tires": model.has_tires,
        "tire_positions_required": model.tire_positions_required,
        "axle_count": model.axle_count,
        "tire_size": model.tire_size,
        "has_batteries": model.has_batteries,
        "battery_count_required": model.battery_count_required,
        "battery_capacity_ah": model.battery_capacity_ah,
        "battery_voltage_v": model.battery_voltage_v,
        "mobility_type": model.mobility_type,
        "requires_driver": model.requires_driver,
        "positions": [
            {
                "id": position.id,
                "axle_number": position.axle_number,
                "side": position.side,
                "position_type": position.position_type,
                "description": position.description,
            }
            for position in db.query(TirePosition)
            .filter(TirePosition.equipment_model_id == model.id)
            .order_by(TirePosition.axle_number, TirePosition.sort_order, TirePosition.id)
            .all()
        ],
        "sizes": [
            row.size
            for row in db.query(TireModelSize)
            .filter(TireModelSize.equipment_model_id == model.id)
            .order_by(TireModelSize.id)
            .all()
        ],
        "specs": [
            {"definition_id": value.spec_definition_id, "value": value.value}
            for value in model.spec_values
        ],
    }


def model_editor_payloads(db: Session, models: list[EquipmentModel]) -> list[dict]:
    return [model_editor_payload(db, model) for model in models]
