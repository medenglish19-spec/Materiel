# Add the missing validate_operation_applicable_to_equipment function to services.py

with open('app/modules/maintenance/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where to insert - after priority_for
insert_after = "def priority_for(state, remaining_meter, meta):"

idx = content.find(insert_after)
if idx >= 0:
    # Find the end of the function
    idx2 = content.find('\ndef ', idx + 1)
    if idx2 < 0:
        idx2 = len(content)
    
    new_func = '''

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

'''
    
    # Insert after the function
    new_content = content[:idx2] + new_func + content[idx2:]
    with open('app/modules/maintenance/services.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("validate_operation_applicable_to_equipment function added successfully!")
else:
    print("Could not find priority_for")