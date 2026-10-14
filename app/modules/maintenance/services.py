from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.modules.maintenance.models import (
    MaintenanceRecord,
    MaintenanceOperation,
    MaintenancePlanOperation,
    MaintenancePlan,
    maintenance_operation_models,
)
from app.modules.meter_readings.models import MeterReading

CONDITION_UNSET = "unset"
CONDITION_MODEL = "model"

CONDITION_UNSET_LABEL = "الشرط غير محدد"
# علاقة طراز محفوظة لكنها لا تحدد أي فاصل (interval_km/hours/days كلها فارغة):
# تُعرض «غير محدد» لا «بدون فاصل محدد»، دون اعتبارها شرطًا مفعّلًا أو استنتاج فاصل.
CONDITION_NO_INTERVAL_LABEL = "غير محدد"
MULTIPLE_CONDITIONS_LABEL = "شروط متعددة"
MULTIPLE_WARNINGS_LABEL = "إعدادات متعددة"
NO_WARNING_LABEL = "بدون إنذار مفعّل"
NO_MODELS_LABEL = "لا توجد طرازات مرتبطة"


def maintenance_record_has_execution_data(record: MaintenanceRecord) -> bool:
    """Distinguish actual maintenance data from a scheduled placeholder."""
    return not record.is_scheduled or record.status != "scheduled"


def maintenance_record_delete_reason(record: MaintenanceRecord) -> str | None:
    """Allow scheduled placeholders and completed records to be deleted."""
    if (record.is_scheduled and record.status == "scheduled") or record.status == "completed":
        return None
    if maintenance_record_has_execution_data(record):
        return "لا يمكن حذف سجل صيانة بهذه الحالة."
    return None


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
    rows = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.is_scheduled.is_(False),
    ).order_by(
        MaintenanceRecord.equipment_id,
        desc(MaintenanceRecord.maintenance_date),
        desc(MaintenanceRecord.id),
    ).all()
    for row in rows:
        key = (row.equipment_id, row.operation_id)
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
    from app.modules.equipment.models import Equipment
    from app.modules.meter_readings.services import validate_meter_observation
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        return "العتاد غير موجود"
    unit = equipment.equipment_type.measurement_unit if equipment.equipment_type else "hours"
    reference = None
    if exclude_id is not None:
        existing_record = db.get(MaintenanceRecord, exclude_id)
        if existing_record is not None:
            from app.modules.meter_readings.source_values import source_reference

            reference = source_reference(existing_record, "meter_value")
    try:
        validate_meter_observation(db, equipment_id, maintenance_date, meter, unit, "الصيانة", source_reference=reference)
    except ValueError as exc:
        return str(exc)
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


def status_for(obj, equipment, record, current_value, plan_operation=None, today=None, condition=None):
    """Calculate due state with independent km, hours, and calendar axes.

    The first argument can be a MaintenanceOperation or MaintenancePlan.
    Warning settings are unified at the operation level.
    Interval settings come from the condition (for operations) or the plan/operation itself (for plans).
    """
    if record is None:
        return "بلا سجل", "neutral", None, {"remaining_days": None, "next_meter": None, "next_date": None, "remaining_km": None, "remaining_hours": None}
    today = today or date.today()
    
    # Interval settings: use condition if provided (for operations with per-model conditions),
    # otherwise fall back to the object (plan or legacy operation)
    if condition is not None:
        interval_km = getattr(condition, "interval_km", None)
        interval_hours = getattr(condition, "interval_hours", None)
        interval_days = getattr(condition, "interval_days", None)
    else:
        interval_km = getattr(obj, "interval_km", None)
        interval_hours = getattr(obj, "interval_hours", None)
        interval_days = getattr(obj, "interval_days", None)
    
    # Warning settings are unified at the operation level (or plan level for plans)
    warning_km = getattr(obj, "warning_km", None)
    warning_days = getattr(obj, "warning_days", None)
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
    """Calculate the plan trigger from the plan's own cadence.

    The plan cadence is the single source of truth for the plan and for its
    member operations: each plan operation is evaluated inside its plan context
    with the plan's condition, not an independent operation condition.
    """
    return status_for(plan, equipment, last_record, current_value, today=today)


def effective_plans_for_equipment(db: Session, equipment):
    """Return active maintenance plans configured for the equipment model."""
    model_id = getattr(equipment, "equipment_model_id", None)
    if model_id is None:
        return []
    return (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.equipment_model_id == model_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        )
        .order_by(MaintenancePlan.name, MaintenancePlan.id)
        .all()
    )


def latest_plan_records(db: Session):
    """Return the latest execution record for each equipment/plan pair."""
    result = {}
    rows = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.plan_id.is_not(None),
        MaintenanceRecord.is_scheduled.is_(False),
    ).order_by(
        MaintenanceRecord.equipment_id,
        desc(MaintenanceRecord.maintenance_date),
        desc(MaintenanceRecord.id),
    ).all()
    for row in rows:
        key = (row.equipment_id, row.plan_id)
        if key not in result:
            result[key] = row
    return result

def effective_operations_for_equipment(db: Session, equipment, include_standalone=False):
    """Return active operations applicable to the equipment model.

    Operations are included only if they have an explicit relationship
    to the equipment model via maintenance_operation_models.
    Plan membership and approval status are separate administrative concepts.
    """
    model_id = getattr(equipment, "equipment_model_id", None)
    if model_id is None:
        return []

    # Get operations explicitly linked to this model
    rows = (
        db.query(MaintenanceOperation)
        .join(
            MaintenanceOperation.equipment_models
        )
        .filter(
            MaintenanceOperation.is_active.is_(True),
            MaintenanceOperation.equipment_models.any(id=model_id),
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

    # Standalone operations (not linked to any model) are NOT included by default.
    # They must be explicitly linked to a model to be applicable.
    if include_standalone:
        standalone = (
            db.query(MaintenanceOperation)
            .filter(
                MaintenanceOperation.is_active.is_(True),
                ~MaintenanceOperation.equipment_models.any(),
            )
            .order_by(MaintenanceOperation.name, MaintenanceOperation.id)
            .all()
        )
        for operation in standalone:
            if operation.id not in seen:
                seen.add(operation.id)
                result.append(operation)

    return sorted(result, key=lambda operation: (operation.name, operation.id))


# ---------------------------------------------------------------------------
# Per-model eligibility conditions
#
# A condition belongs to the operation↔model relation, not to the shared
# operation. Resolution below never reads the operation's own
# `interval_*` / `warning_*` columns and never reads another model's row: those
# legacy shared columns are ignored by every calculation, alert and operational
# view, and are kept in the database untouched. An operation with no model
# relation is a general library entry: it produces no due state and no alert,
# and a relation without a stored condition reports «الشرط غير محدد».
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelCondition:
    """Eligibility condition of one operation for one equipment model.
    
    Warning settings are unified at the operation level (MaintenanceOperation).
    """

    operation_id: int | None = None
    equipment_model_id: int | None = None
    condition_source: str = CONDITION_UNSET
    interval_km: Decimal | None = None
    interval_hours: Decimal | None = None
    interval_days: int | None = None
    is_active: bool = True

    @property
    def is_defined(self) -> bool:
        return self.condition_source == CONDITION_MODEL

    @property
    def has_interval(self) -> bool:
        return (
            self.interval_km is not None
            or self.interval_hours is not None
            or self.interval_days is not None
        )

    def without_condition(self) -> "ModelCondition":
        """The same relation with its stored condition cleared."""
        return replace(
            self,
            condition_source=CONDITION_UNSET,
            interval_km=None,
            interval_hours=None,
            interval_days=None,
        )


def _condition_from_row(row) -> ModelCondition:
    return ModelCondition(
        operation_id=row.operation_id,
        equipment_model_id=row.equipment_model_id,
        condition_source=(row.condition_source or CONDITION_UNSET),
        interval_km=row.interval_km,
        interval_hours=row.interval_hours,
        interval_days=row.interval_days,
        is_active=bool(row.is_active),
    )


def _condition_rows(db: Session, operation_id: int, equipment_model_id: int | None = None):
    query = select(maintenance_operation_models).where(
        maintenance_operation_models.c.operation_id == operation_id,
    )
    if equipment_model_id is not None:
        query = query.where(
            maintenance_operation_models.c.equipment_model_id == equipment_model_id
        )
    return db.execute(query).all()


def operation_condition_for_model(db: Session, operation_id: int, equipment_model_id: int | None) -> ModelCondition:
    """Condition stored for one operation on one model.

    Returns an unset condition (never a copied default) when the model is
    unknown or has no condition configured yet.
    """
    if operation_id is None or equipment_model_id is None:
        return ModelCondition(operation_id=operation_id, equipment_model_id=equipment_model_id)
    rows = _condition_rows(db, operation_id, equipment_model_id)
    if not rows:
        return ModelCondition(operation_id=operation_id, equipment_model_id=equipment_model_id)
    return _condition_from_row(rows[0])


def operation_conditions_by_model(db: Session, operation_ids) -> dict:
    """Every stored condition of the given operations, keyed by (operation_id, model_id).

    One query for the whole page — the rules table and the due engine must not
    issue a query per operation and per model.
    """
    ids = [int(operation_id) for operation_id in operation_ids if operation_id is not None]
    if not ids:
        return {}
    rows = db.execute(
        select(maintenance_operation_models).where(
            maintenance_operation_models.c.operation_id.in_(ids)
        )
    ).all()
    return {(row.operation_id, row.equipment_model_id): _condition_from_row(row) for row in rows}


def condition_for_equipment(db: Session, operation, equipment) -> ModelCondition:
    """The condition of one standalone operation: the equipment's own model row.

    This is the operation-level view: it never returns a plan's cadence. Plan
    members are evaluated per plan through `operation_tasks_for_model`, which
    carries each plan's condition explicitly.
    """
    model_id = getattr(equipment, "equipment_model_id", None)
    return operation_condition_for_model(db, getattr(operation, "id", None), model_id)


# ---------------------------------------------------------------------------
# Plan context: a plan's cadence is the eligibility condition of its operations
#
# A plan operation does not need an independent per-model condition to become a
# member of a plan: inside its plan it is evaluated against the plan's condition,
# which stays the single source of truth for that plan. Nothing is written back
# to the shared operation or to the operation↔model relation, so changing one
# plan never touches a standalone condition, the library definition, or another
# plan's context.
# ---------------------------------------------------------------------------


def plan_condition(plan) -> ModelCondition:
    """The plan's cadence expressed as the condition governing its operations.

    Returns an unset condition when the plan defines no interval, so a plan
    operation is never evaluated against an invented cadence. The result is a
    value derived from the plan at read time; it is never persisted.
    """
    if plan is None:
        return ModelCondition(condition_source=CONDITION_UNSET)
    if plan.interval_km is None and plan.interval_hours is None and plan.interval_days is None:
        return ModelCondition(condition_source=CONDITION_UNSET)
    return ModelCondition(
        equipment_model_id=getattr(plan, "equipment_model_id", None),
        condition_source=CONDITION_MODEL,
        interval_km=plan.interval_km,
        interval_hours=plan.interval_hours,
        interval_days=plan.interval_days,
    )


@dataclass(frozen=True)
class MaintenanceTask:
    """One follow-up context of one equipment model.

    `plan` is set for a member of an approved, active plan — the operation then
    inherits the plan's condition. `plan` is None for a standalone operation,
    which keeps its own per-model condition.
    """

    operation: "MaintenanceOperation"
    plan: "MaintenancePlan | None"
    condition: ModelCondition


def operation_tasks_for_model(db: Session, equipment_model_id: int | None) -> list:
    """Every maintenance follow-up of one equipment model.

    Built once per model so the periodic, due and notification views never issue
    a query per operation:

    * one task per active operation of an approved, active plan, governed by the
      plan's condition;
    * one standalone task per active operation linked to the model that is not a
      member of any approved, active plan, governed by its own model condition.
    """
    if equipment_model_id is None:
        return []

    plans = (
        db.query(MaintenancePlan)
        .filter(
            MaintenancePlan.equipment_model_id == equipment_model_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        )
        .order_by(MaintenancePlan.name, MaintenancePlan.id)
        .all()
    )

    tasks: list = []
    planned_operation_ids: set = set()
    if plans:
        plan_by_id = {plan.id: plan for plan in plans}
        links = (
            db.query(MaintenancePlanOperation)
            .options(joinedload(MaintenancePlanOperation.operation))
            .join(
                MaintenanceOperation,
                MaintenanceOperation.id == MaintenancePlanOperation.operation_id,
            )
            .filter(
                MaintenancePlanOperation.plan_id.in_(list(plan_by_id)),
                MaintenanceOperation.is_active.is_(True),
            )
            .order_by(MaintenancePlanOperation.sort_order, MaintenancePlanOperation.id)
            .all()
        )
        for link in links:
            plan = plan_by_id.get(link.plan_id)
            operation = link.operation
            if plan is None or operation is None:
                continue
            planned_operation_ids.add(operation.id)
            tasks.append(
                MaintenanceTask(
                    operation=operation,
                    plan=plan,
                    condition=plan_condition(plan),
                )
            )

    linked_operations = (
        db.query(MaintenanceOperation)
        .join(MaintenanceOperation.equipment_models)
        .filter(
            MaintenanceOperation.is_active.is_(True),
            MaintenanceOperation.equipment_models.any(id=equipment_model_id),
        )
        .order_by(MaintenanceOperation.name, MaintenanceOperation.id)
        .all()
    )
    standalone: list = []
    seen: set = set()
    for operation in linked_operations:
        if operation.id in planned_operation_ids or operation.id in seen:
            continue
        seen.add(operation.id)
        standalone.append(operation)

    conditions = operation_conditions_by_model(db, [operation.id for operation in standalone])
    for operation in standalone:
        condition = conditions.get(
            (operation.id, equipment_model_id),
            ModelCondition(operation_id=operation.id, equipment_model_id=equipment_model_id),
        )
        tasks.append(MaintenanceTask(operation=operation, plan=None, condition=condition))

    return tasks


def operation_tasks_for_equipment(db: Session, equipment) -> list:
    """The maintenance follow-ups of one equipment, by its own model."""
    return operation_tasks_for_model(db, getattr(equipment, "equipment_model_id", None))


def meter_required_for_condition(condition, unit: str) -> bool:
    """Does one model's condition make an odometer/hour reading mandatory?

    The equipment's own model condition decides, per axis: a model whose stored
    condition has no interval on this equipment's unit axis does not require a
    reading. This keeps one policy across the app — the same rule that makes an
    unset model report «الشرط غير محدد» instead of being measured against a value
    nobody stored for it.
    """
    if unit == "km":
        return getattr(condition, "interval_km", None) is not None
    if unit == "hours":
        return getattr(condition, "interval_hours", None) is not None
    return False


def condition_without_interval(condition: ModelCondition | None) -> bool:
    """True when the condition is configured but defines no interval axis."""
    if condition is None:
        return True
    return condition.is_defined and not condition.has_interval


def check_plan_operation_condition_compatibility(plan, model_condition: ModelCondition | None) -> str | None:
    """Compare a plan's own cadence with one model's operation condition.

    A plan is bound to a single equipment model, so it must be checked against
    that model's condition only — never against a single operation-wide value.
    """
    if model_condition is None or not model_condition.is_defined:
        return f"{CONDITION_UNSET_LABEL} لهذا الطراز؛ لا يمكن مقارنته بشرط الخطة"
    if not model_condition.has_interval:
        return "شرط الطراز لا يحدد أي فاصل صيانة؛ لا يمكن مقارنته بشرط الخطة"
    return check_plan_operation_compatibility(plan, model_condition)


def _number(value) -> str:
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


def condition_axis_text(condition: ModelCondition | None) -> str:
    """Human summary of the stored interval axes of one model condition.

    Only a condition stored on the operation↔model relation is rendered. The
    operation's own `interval_*` columns are not a model condition and are not
    shown here at all.
    """
    if condition is None or not condition.is_defined:
        return "—"
    parts = []
    if condition.interval_km is not None:
        parts.append(f"{_number(condition.interval_km)} كم")
    if condition.interval_hours is not None:
        parts.append(f"{_number(condition.interval_hours)} ساعة")
    if condition.interval_days is not None:
        parts.append(f"{condition.interval_days} يوم")
    if not parts:
        return CONDITION_NO_INTERVAL_LABEL
    return " أو ".join(parts)


def condition_axis_units(condition: ModelCondition | None) -> list:
    """Unit keys of the stored interval axes, in display order."""
    if condition is None or not condition.is_defined:
        return []
    units = []
    if condition.interval_km is not None:
        units.append("km")
    if condition.interval_hours is not None:
        units.append("hours")
    if condition.interval_days is not None:
        units.append("days")
    return units


_UNIT_LABELS = {"km": "كم", "hours": "ساعة", "days": "يوم"}


def condition_unit_text(condition: ModelCondition | None) -> str:
    units = condition_axis_units(condition)
    if not units:
        return "—"
    return " / ".join(_UNIT_LABELS[unit] for unit in units)


def warning_setting_text(operation, condition: ModelCondition | None, reference: bool = False) -> str:
    """Warning setting of one operation.

    Warning is unified at the operation level. Per-model conditions don't carry warnings.
    For unset conditions, return "—" regardless of operation warnings.
    If condition is None (not a model condition), return the operation's warning.
    """
    # If condition is None (not a model condition), return operation warning
    if condition is None:
        if operation is None:
            return "—"
        warning_km = getattr(operation, "warning_km", None)
        warning_days = getattr(operation, "warning_days", None)
        if warning_km is None and warning_days is None:
            return NO_WARNING_LABEL
        parts = []
        if warning_km is not None:
            parts.append(f"{_number(warning_km)} كم")
        if warning_days is not None:
            parts.append(f"{warning_days} يوم")
        if not parts:
            return NO_WARNING_LABEL
        return " / ".join(parts)
    
    # For unset or undefined model conditions, return "—"
    if not condition.is_defined:
        return "—"
    
    # For defined model conditions, return operation warning
    if operation is None:
        return "—"
    
    warning_km = getattr(operation, "warning_km", None)
    warning_days = getattr(operation, "warning_days", None)
    
    if warning_km is None and warning_days is None:
        return NO_WARNING_LABEL
    parts = []
    if warning_km is not None:
        parts.append(f"{_number(warning_km)} كم")
    if warning_days is not None:
        parts.append(f"{warning_days} يوم")
    if not parts:
        return NO_WARNING_LABEL
    return " / ".join(parts)


def _distinct(values) -> list:
    distinct = []
    for value in values:
        if value not in distinct:
            distinct.append(value)
    return distinct


def summarize_operation_conditions(condition_rows: list) -> dict:
    """Summary of the models' conditions for the operations table.

    Each entry describes one operation and carries already-computed display
    strings, so the table never has to reinterpret a condition on its own:

    * no linked model      → no condition and no warning is shown at all;
    * one or more models, all with the same stored condition → that condition;
    * models with different conditions → «شروط متعددة» + per-model details;
    * at least one model without a stored condition → «الشرط غير محدد», and no
      value is inferred from the other models.
    """
    summary = {
        "models_count": len(condition_rows),
        "defined_count": 0,
        "unset_count": 0,
        "condition": None,
        "condition_state": "no_models",
        "warning": None,
        "warning_state": "no_models",
        "unit": None,
        "has_multiple_conditions": False,
        "has_multiple_warnings": False,
    }
    if not condition_rows:
        return summary

    defined = [row for row in condition_rows if row["is_defined"]]
    summary["defined_count"] = len(defined)
    summary["unset_count"] = len(condition_rows) - len(defined)

    units = _distinct(
        unit
        for row in defined
        for unit in row.get("condition_units", [])
    )
    summary["unit"] = " / ".join(_UNIT_LABELS[unit] for unit in units) if units else "—"

    if summary["unset_count"]:
        summary["condition"] = CONDITION_UNSET_LABEL
        summary["condition_state"] = "unset" if not defined else "partially_unset"
    else:
        texts = _distinct(row["condition_text"] for row in defined)
        if len(texts) == 1:
            summary["condition"] = texts[0]
            summary["condition_state"] = "shared"
        else:
            summary["condition"] = MULTIPLE_CONDITIONS_LABEL
            summary["condition_state"] = "multiple"
            summary["has_multiple_conditions"] = True

    warning_texts = _distinct(row["warning_text"] for row in defined)
    if len(warning_texts) == 1:
        summary["warning"] = warning_texts[0]
        summary["warning_state"] = "shared"
    elif len(warning_texts) > 1:
        summary["warning"] = MULTIPLE_WARNINGS_LABEL
        summary["warning_state"] = "multiple"
        summary["has_multiple_warnings"] = True
    else:
        summary["warning"] = NO_WARNING_LABEL
        summary["warning_state"] = "shared"

    return summary


def operation_condition_details(db: Session, operation) -> list:
    """Per-model condition rows behind the rules table's condition column."""
    models = sorted(operation.equipment_models, key=lambda model: (model.name or "", model.id))
    conditions = operation_conditions_by_model(db, [operation.id])
    rows = []
    for model in models:
        condition = conditions.get((operation.id, model.id), ModelCondition(operation_id=operation.id, equipment_model_id=model.id))
        rows.append(
            {
                "model_id": model.id,
                "model_name": model.name,
                "is_defined": condition.is_defined,
                "condition_source": condition.condition_source,
                "interval_km": condition.interval_km,
                "interval_hours": condition.interval_hours,
                "interval_days": condition.interval_days,
                "condition_text": condition_axis_text(condition),
                "condition_units": condition_axis_units(condition),
                "unit_text": condition_unit_text(condition),
                "warning_text": warning_setting_text(operation, condition),
            }
        )
    return rows


def operation_condition_entries(db: Session, operation) -> list:
    """Details of every model relation of one operation."""
    return operation_condition_details(db, operation)


def operation_condition_summary(db: Session, operation) -> dict:
    return summarize_operation_conditions(operation_condition_details(db, operation))


def operations_payload(db: Session, operations: list) -> list:
    """Serialize operations with their per-model conditions for the JSON API.

    Only conditions stored on the operation↔model relation are exposed. The
    operation's own `interval_*` / `warning_*` columns are legacy shared values
    that no calculation uses, so they are not sent as a model condition nor as a
    reference the UI is expected to copy.
    
    Warning settings are unified at the operation level and included in the payload.
    """
    def _to_float(value):
        """Convert Decimal to float for JSON serialization."""
        if isinstance(value, Decimal):
            return float(value)
        return value

    operations = list(operations)
    conditions = operation_conditions_by_model(db, [operation.id for operation in operations])
    payload = []
    for operation in operations:
        details = []
        for model in sorted(operation.equipment_models, key=lambda model: (model.name or "", model.id)):
            condition = conditions.get(
                (operation.id, model.id),
                ModelCondition(operation_id=operation.id, equipment_model_id=model.id),
            )
            details.append(
                {
                    "model_id": model.id,
                    "model_name": model.name,
                    "is_defined": condition.is_defined,
                    "condition_source": condition.condition_source,
                    "interval_km": _to_float(condition.interval_km),
                    "interval_hours": _to_float(condition.interval_hours),
                    "interval_days": _to_float(condition.interval_days),
                    "condition_text": condition_axis_text(condition),
                    "condition_units": condition_axis_units(condition),
                    "unit_text": condition_unit_text(condition),
                    "warning_text": warning_setting_text(operation, condition),
                }
            )
        # Determine condition_source: "model_conditions" if any model has a stored condition (defined), else "none"
        # An operation with only "unset" model conditions (no stored rows) should report "none"
        has_stored_condition = any(d["condition_source"] != "unset" for d in details)
        condition_source = "model_conditions" if has_stored_condition else "none"
        
        # Operation-level warning settings (unified across all models)
        warning_km = getattr(operation, "warning_km", None)
        warning_days = getattr(operation, "warning_days", None)
        
        # Build condition summary, then override warning with operation-level warning if applicable
        condition_summary = summarize_operation_conditions(details)
        # If operation has a warning, use operation warning (warnings are unified at operation level)
        # This applies even when there are no linked models
        if warning_km is not None or warning_days is not None:
            op_warning = warning_setting_text(operation, None)  # None condition -> returns operation warning
            condition_summary["warning"] = op_warning
            condition_summary["warning_state"] = "shared"
            condition_summary["has_multiple_warnings"] = False
        
        payload.append(
            {
                "id": operation.id,
                "name": operation.name,
                "group_id": operation.group_id,
                "description": operation.description,
                "is_active": bool(operation.is_active),
                "warning_km": _to_float(warning_km),
                "warning_days": _to_float(warning_days),
                "model_conditions": details,
                "condition_summary": condition_summary,
                "condition_source": condition_source,
            }
        )
    return payload


def operation_condition_meta(operation, condition, equipment, record, current_value, today=None):
    """Due state of one operation under one model's condition.

    The engine refuses to invent a condition: an unset or interval-less model
    condition yields an explicit "not computed" state. The operation's legacy
    shared columns are never consulted, so they cannot produce a due state.
    
    Warning settings are unified at the operation level.
    """
    if condition is None or not condition.is_defined or not condition.has_interval:
        return (
            CONDITION_UNSET_LABEL,
            "neutral",
            None,
            {
                "remaining_days": None,
                "next_meter": None,
                "next_date": None,
                "remaining_km": None,
                "remaining_hours": None,
                "condition_unset": True,
            },
        )
    return status_for(operation, equipment, record, current_value, today=today, condition=condition)

def priority_for(state, remaining_meter, meta):
    if state == "مستحقة الآن":
        return 1
    if state == "تقترب":
        return 2
    if state == "بلا سجل":
        return 3
    candidates = [x for x in (remaining_meter, meta.get("remaining_days")) if x is not None]
    return 4 if candidates else 5


def check_plan_operation_compatibility(plan, operation):
    """Check if operation's conditions are compatible with plan's conditions.
    Returns error message if incompatible, None if compatible.

    This is the single source of truth for plan-operation compatibility validation.
    """
    # Check if both have interval_km
    if plan.interval_km is not None and operation.interval_km is not None:
        if plan.interval_km != operation.interval_km:
            return f"شرط العملية ({operation.interval_km} كم) لا يطابق شرط الخطة ({plan.interval_km} كم)"
    elif plan.interval_km is not None and operation.interval_km is None:
        return f"الخطة تشترط كيلومترات ({plan.interval_km} كم) لكن العملية لا تحدد شرط كيلومترات"
    elif plan.interval_km is None and operation.interval_km is not None:
        return f"العملية تشترط كيلومترات ({operation.interval_km} كم) لكن الخطة لا تحدد شرط كيلومترات"

    # Check if both have interval_hours
    if plan.interval_hours is not None and operation.interval_hours is not None:
        if plan.interval_hours != operation.interval_hours:
            return f"شرط العملية ({operation.interval_hours} ساعة) لا يطابق شرط الخطة ({plan.interval_hours} ساعة)"
    elif plan.interval_hours is not None and operation.interval_hours is None:
        return f"الخطة تشترط ساعات تشغيل ({plan.interval_hours} ساعة) لكن العملية لا تحدد شرط ساعات"
    elif plan.interval_hours is None and operation.interval_hours is not None:
        return f"العملية تشترط ساعات تشغيل ({operation.interval_hours} ساعة) لكن الخطة لا تحدد شرط ساعات"

    # Check if both have interval_days
    if plan.interval_days is not None and operation.interval_days is not None:
        if plan.interval_days != operation.interval_days:
            return f"شرط العملية ({operation.interval_days} يوم) لا يطابق شرط الخطة ({plan.interval_days} يوم)"
    elif plan.interval_days is not None and operation.interval_days is None:
        return f"الخطة تشترط أيام ({plan.interval_days} يوم) لكن العملية لا تحدد شرط أيام"
    elif plan.interval_days is None and operation.interval_days is not None:
        return f"العملية تشترط أيام ({operation.interval_days} يوم) لكن الخطة لا تحدد شرط أيام"

    # Check that they have the same type of condition (at least one matching non-null)
    plan_conditions = [c for c in [plan.interval_km, plan.interval_hours, plan.interval_days] if c is not None]
    op_conditions = [c for c in [operation.interval_km, operation.interval_hours, operation.interval_days] if c is not None]

    if not plan_conditions:
        return "الخطة لا تحدد أي شرط صيانة"

    # At least one condition type must match
    matching_types = 0
    if plan.interval_km is not None and operation.interval_km is not None:
        matching_types += 1
    if plan.interval_hours is not None and operation.interval_hours is not None:
        matching_types += 1
    if plan.interval_days is not None and operation.interval_days is not None:
        matching_types += 1

    if matching_types == 0:
        return "نوع شرط العملية لا يتطابق مع نوع شرط الخطة"

    return None


def validate_operation_applicable_to_equipment(db: Session, operation: MaintenanceOperation, equipment) -> str | None:
    """Validate that an operation is applicable to the given equipment.
    
    Returns error message if not applicable, None if applicable.
    """
    if operation is None:
        return "يجب تحديد عملية الصيانة."
    if not operation.is_active:
        return "عملية الصيانة غير مفعلة."
    
    equipment_model_id = getattr(equipment, "equipment_model_id", None)
    if equipment_model_id is None:
        return "طراز العتاد غير محدد."
    
    model_linked = any(m.id == equipment_model_id for m in operation.equipment_models)
    if not model_linked:
        return "عملية الصيانة لا تنطبق على طراز هذا العتاد."
    
    return None
