from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.modules.maintenance.models import MaintenanceRecord, MaintenanceRule, MaintenanceOperation, MaintenancePlanOperation, MaintenancePlan
from app.modules.meter_readings.models import MeterReading


def latest_readings(db: Session):
    readings = {}
    rows = db.query(MeterReading).order_by(
        MeterReading.equipment_id,
        desc(MeterReading.reading_date),
        desc(MeterReading.id),
    ).all()
    for row in rows:
        if row.equipment_id not in readings:
            readings[row.equipment_id] = row
    return readings


def latest_records(db: Session):
    result = {}
    rows = db.query(MaintenanceRecord).order_by(
        MaintenanceRecord.equipment_id,
        desc(MaintenanceRecord.maintenance_date),
        desc(MaintenanceRecord.id),
    ).all()
    for row in rows:
        key = (row.equipment_id, row.operation_id or row.rule_id)
        if key not in result:
            result[key] = row
    return result


def measurement_unit(equipment):
    return (equipment.equipment_type.measurement_unit or "").strip().lower()


def current_meter_value(equipment, reading):
    unit = measurement_unit(equipment)
    if unit == "hours":
        return equipment.current_hours if equipment.current_hours is not None else (reading.hours if reading else None)
    return equipment.current_odometer if equipment.current_odometer is not None else (reading.odometer if reading else None)


def chronology_error(db: Session, equipment_id: int, maintenance_date: date, meter: Decimal | None, exclude_id=None):
    if meter is None:
        return None
    records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.equipment_id == equipment_id,
        MaintenanceRecord.meter_value.is_not(None),
    ).order_by(MaintenanceRecord.maintenance_date, MaintenanceRecord.id).all()
    for row in records:
        if exclude_id is not None and row.id == exclude_id:
            continue
        if row.maintenance_date < maintenance_date and meter < Decimal(str(row.meter_value)):
            return "قراءة العداد أقل من قراءة سجل صيانة أقدم"
        if row.maintenance_date > maintenance_date and meter > Decimal(str(row.meter_value)):
            return "قراءة العداد أكبر من قراءة سجل صيانة أحدث"
    return None


def contradiction_for(equipment, record, current_value, db):
    if record is None or record.meter_value is None:
        return None
    error = chronology_error(
        db,
        equipment.id,
        record.maintenance_date,
        Decimal(str(record.meter_value)),
        exclude_id=record.id,
    )
    if error:
        return f"⚠ {error}"
    if current_value is not None and record.meter_value > current_value:
        return "⚠ آخر صيانة تحمل عدادًا أكبر من العداد الحالي"
    return None


def status_for(condition, equipment, record, current_value, plan_operation=None, today=None):
    """Calculate due state with independent km, hours, and calendar axes."""
    if record is None:
        return "بلا سجل", "neutral", None, {"remaining_days": None, "next_meter": None, "next_date": None, "remaining_km": None, "remaining_hours": None}
    today = today or date.today()
    interval_km = getattr(condition, "interval_km", None)
    interval_hours = getattr(condition, "interval_hours", None)
    interval_days = getattr(condition, "interval_days", None)
    warning_km = getattr(condition, "warning_km", None)
    warning_days = getattr(condition, "warning_days", None)
    unit = measurement_unit(equipment)
    current = Decimal(str(current_value)) if current_value is not None else None
    meter_at_service = Decimal(str(record.meter_value)) if record.meter_value is not None else None
    next_km = meter_at_service + Decimal(str(interval_km)) if interval_km is not None and meter_at_service is not None else None
    next_hours = meter_at_service + Decimal(str(interval_hours)) if interval_hours is not None and meter_at_service is not None else None
    next_date = record.maintenance_date + timedelta(days=int(interval_days)) if interval_days is not None else None
    remaining_km = next_km - current if next_km is not None and current is not None and unit == "km" else None
    remaining_hours = next_hours - current if next_hours is not None and current is not None and unit == "hours" else None
    remaining_days = (next_date - today).days if next_date is not None else None
    remaining_meter = remaining_km if unit == "km" else remaining_hours
    warning_meter = warning_km if unit == "km" else None
    overdue_meter = remaining_meter is not None and remaining_meter <= 0
    overdue_days = remaining_days is not None and remaining_days <= 0
    near_meter = warning_meter is not None and remaining_meter is not None and remaining_meter <= Decimal(str(warning_meter))
    near_days = warning_days is not None and remaining_days is not None and remaining_days <= int(warning_days)
    meta = {"remaining_days": remaining_days, "next_meter": next_km if unit == "km" else next_hours, "next_date": next_date, "remaining_km": remaining_km, "remaining_hours": remaining_hours}
    if overdue_meter or overdue_days:
        return "مستحقة الآن", "danger", remaining_meter, meta
    if near_meter or near_days:
        return "تقترب", "warning", remaining_meter, meta
    return "ضمن الموعد", "success", remaining_meter, meta


def plan_status_for(plan, equipment, last_record, current_value, today=None):
    """Calculate the plan trigger independently from operation due status.

    Plan cadence fields are used only for plan-level due/display state;
    operation-specific conditions remain authoritative for each operation.
    """
    return status_for(plan, equipment, last_record, current_value, today=today)


def effective_operations_for_equipment(db: Session, equipment, include_standalone=True):
    """Return active operations applicable to the equipment model.

    Planned operations come from active plans for the model. Standalone
    operations are included when requested. Plan membership does not alter
    the operation's own technical condition.
    """
    model_id = getattr(equipment, "equipment_model_id", None)
    if model_id is None:
        return []

    rows = (
        db.query(MaintenanceOperation)
        .join(MaintenancePlanOperation, MaintenancePlanOperation.operation_id == MaintenanceOperation.id)
        .join(MaintenancePlan, MaintenancePlan.id == MaintenancePlanOperation.plan_id)
        .filter(
            MaintenanceOperation.is_active.is_(True),
            MaintenancePlan.equipment_model_id == model_id,
            MaintenancePlan.is_active.is_(True),
        )
        .order_by(MaintenanceOperation.name, MaintenanceOperation.id)
        .all()
    )

    seen = set()
    result = []
    for operation in rows:
        if operation.id not in seen:
            seen.add(operation.id)
            result.append(operation)

    if include_standalone:
        standalone = (
            db.query(MaintenanceOperation)
            .filter(
                MaintenanceOperation.is_active.is_(True),
                ~MaintenanceOperation.plan_operations.any(),
            )
            .order_by(MaintenanceOperation.name, MaintenanceOperation.id)
            .all()
        )
        for operation in standalone:
            if operation.id not in seen:
                seen.add(operation.id)
                result.append(operation)

    return sorted(result, key=lambda operation: (operation.name, operation.id))

def priority_for(state, remaining_meter, meta):
    if state == "مستحقة الآن":
        return 1
    if state == "تقترب":
        return 2
    if state == "بلا سجل":
        return 3
    candidates = [x for x in (remaining_meter, meta.get("remaining_days")) if x is not None]
    return 4 if candidates else 5


def effective_rules_for_equipment(db: Session, equipment, include_rule_id=None):
    """Return only maintenance rules assigned to the equipment's model.

    Classification, brand, and equipment type never select a maintenance rule.
    The type is used only to determine the meter unit through the equipment itself.
    """
    model_id = getattr(equipment, "equipment_model_id", None)
    if model_id is None:
        return []

    query = (
        db.query(MaintenanceRule)
        .options(
            joinedload(MaintenanceRule.equipment_type),
            joinedload(MaintenanceRule.equipment_model),
        )
        .filter(
            MaintenanceRule.equipment_model_id == model_id,
            MaintenanceRule.is_active.is_(True),
        )
        .order_by(MaintenanceRule.name, MaintenanceRule.id)
    )
    result = query.all()

    if include_rule_id is not None and not any(rule.id == include_rule_id for rule in result):
        historical = (
            db.query(MaintenanceRule)
            .options(
                joinedload(MaintenanceRule.equipment_type),
                joinedload(MaintenanceRule.equipment_model),
            )
            .filter(
                MaintenanceRule.id == include_rule_id,
                MaintenanceRule.equipment_model_id == model_id,
            )
            .first()
        )
        if historical is not None:
            result.append(historical)

    return sorted(result, key=lambda rule: (rule.name, rule.id))


def get_effective_rule_for_equipment(db: Session, equipment, rule_id: int, include_historical: bool = False):
    rules = effective_rules_for_equipment(
        db,
        equipment,
        include_rule_id=rule_id if include_historical else None,
    )
    return next((rule for rule in rules if rule.id == rule_id), None)
