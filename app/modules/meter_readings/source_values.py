"""Read domain-event meter values from the central meter ledger."""
from datetime import datetime, timezone
from sqlalchemy.orm import object_session


def source_reference(record, attribute: str) -> str | None:
    name = type(record).__name__
    if name == "FuelRecord":
        return f"fuel:{record.id}:meter" if record.id is not None else None
    if name == "Fault":
        return f"fault:{record.id}:meter" if record.id is not None else None
    if name == "Repair":
        return f"repair:{record.id}:meter" if record.id is not None else None
    if name == "MaintenanceRecord":
        if record.id is None:
            return None
        if record.plan_id is not None:
            return f"maintenance_plan:{record.plan_id}:{record.equipment_id}:{record.maintenance_date}:meter"
        return f"maintenance:{record.id}:meter"
    if name == "Mission":
        return f"mission:{record.id}:{'departure' if attribute == 'departure_meter' else 'return'}" if record.id is not None else None
    if name == "TireMovement":
        return f"tire_movement:{record.id}:meter" if record.id is not None else None
    if name == "BatteryMovement":
        return f"battery_movement:{record.id}:meter" if record.id is not None else None
    return None


def read_source_value(record, attribute: str):
    pending_key = f"_pending_{attribute}"
    if pending_key in record.__dict__:
        return record.__dict__[pending_key]
    reference = source_reference(record, attribute)
    session = object_session(record)
    if reference is None or session is None:
        return None
    from app.modules.meter_readings.models import MeterReading

    reading = session.query(MeterReading).filter(MeterReading.source_reference == reference).first()
    if reading is None:
        return None
    return reading.odometer if reading.odometer is not None else reading.hours


def write_source_value(record, attribute: str, value):
    record.__dict__[f"_pending_{attribute}"] = value
    # The input value itself is transient; touching the mapped audit timestamp
    # schedules ORM update listeners to validate and store it centrally.
    if hasattr(type(record), "updated_at"):
        record.updated_at = datetime.now(timezone.utc)
