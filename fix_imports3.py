with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_imports = '''from app.modules.maintenance.services import (
    check_plan_operation_compatibility,
    check_plan_operation_condition_compatibility,
    chronology_error,
    contradiction_for,
    current_meter_value,
    effective_operations_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    operation_condition_for_model,
    operation_conditions_by_model,
    operations_payload,
    operation_to_api_payload,
    priority_for,
    status_for,
    plan_status_for,
    effective_plans_for_equipment,
    latest_plan_records,
    validate_operation_applicable_to_equipment,
)'''

new_imports = '''from app.modules.maintenance.services import (
    check_plan_operation_compatibility,
    check_plan_operation_condition_compatibility,
    chronology_error,
    contradiction_for,
    current_meter_value,
    effective_operations_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    operation_condition_for_model,
    operation_conditions_by_model,
    operations_payload,
    operations_payload_list,
    operation_to_api_payload,
    priority_for,
    status_for,
    plan_status_for,
    effective_plans_for_equipment,
    latest_plan_records,
    validate_operation_applicable_to_equipment,
)'''

if old_imports in content:
    content = content.replace(old_imports, new_imports)
    with open('app/modules/maintenance/router.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Import updated successfully!")
else:
    print("Old imports not found!")