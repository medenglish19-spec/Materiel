old_bytes = b'''def operations_payload(db: Session, operations: list) -> list:
    """Serialize operations with their per-model conditions for the JSON API.

    Only conditions stored on the operation<->model relation are exposed. The
    operation's own `interval_*` / `warning_*` columns are legacy shared values
    that no calculation uses, so they are not sent as a model condition nor as a
    reference the UI is expected to copy.
    """
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
                    "interval_km": condition.interval_km,
                    "interval_hours": condition.interval_hours,
                    "interval_days": condition.interval_days,
                    "warning_km": condition.warning_km,
                    "warning_days": condition.warning_days,
                    "condition_text": condition_axis_text(condition),
                    "condition_units": condition_axis_units(condition),
                    "unit_text": condition_unit_text(condition),
                    "warning_text": warning_setting_text(condition),
                }
            )
        has_model_conditions = len(details) > 0
        # condition_source is "model_conditions" only if at least one model has a defined condition
        has_defined = any(d["is_defined"] for d in details)
        payload.append(
            {
                "id": operation.id,
                "name": operation.name,
                "group_id": operation.group_id,
                "description": operation.description,
                "is_active": bool(operation.is_active),
                "model_conditions": details,
                "condition_summary": summarize_operation_conditions(details),
                "condition_source": "model_conditions" if has_defined else "none",
            }
        )
    return payload'''

new_bytes = b'''def operations_payload(db: Session, operations: list) -> list:
    """Serialize operations with their per-model conditions for the JSON API.

    Only conditions stored on the operation<->model relation are exposed. The
    operation's own `interval_*` / `warning_*` columns are legacy shared values
    that no calculation uses, so they are not sent as a model condition nor as a
    reference the UI is expected to copy.
    """
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
                    "interval_km": str(condition.interval_km) if condition.interval_km is not None else None,
                    "interval_hours": str(condition.interval_hours) if condition.interval_hours is not None else None,
                    "interval_days": condition.interval_days,
                    "warning_km": str(condition.warning_km) if condition.warning_km is not None else None,
                    "warning_days": condition.warning_days,
                    "condition_text": condition_axis_text(condition),
                    "condition_units": condition_axis_units(condition),
                    "unit_text": condition_unit_text(condition),
                    "warning_text": warning_setting_text(condition),
                }
            )
        has_model_conditions = len(details) > 0
        # condition_source is "model_conditions" only if at least one model has a defined condition
        has_defined = any(d["is_defined"] for d in details)
        payload.append(
            {
                "id": operation.id,
                "name": operation.name,
                "group_id": operation.group_id,
                "description": operation.description,
                "is_active": bool(operation.is_active),
                "model_conditions": details,
                "condition_summary": summarize_operation_conditions(details),
                "condition_source": "model_conditions" if has_defined else "none",
            }
        )
    return payload'''

with open('app/modules/maintenance/services.py', 'rb') as f:
    content = f.read()

if old_bytes in content:
    content = content.replace(old_bytes, new_bytes)
    with open('app/modules/maintenance/services.py', 'wb') as f:
        f.write(content)
    print("Replacement successful!")
else:
    print("Old text not found!")