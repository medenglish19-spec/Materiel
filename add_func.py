# Add the missing function to services.py
# Read the file
with open('app/modules/maintenance/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where to insert - after check_plan_operation_condition_compatibility
insert_after = "def check_plan_operation_condition_compatibility(plan, model_condition: ModelCondition | None) -> str | None:"

# Find the end of that function
idx = content.find(insert_after)
if idx >= 0:
    # Find the next function definition
    idx2 = content.find('\ndef ', idx + 1)
    if idx2 < 0:
        idx2 = len(content)
    
    # Insert after the function
    insert_pos = idx2
    
    new_func = '''

def check_plan_operation_compatibility(plan, operation):
    """Check if operation's conditions are compatible with plan's conditions.
    Returns error message if incompatible, None if compatible.
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

'''
    
    # Find the end of check_plan_operation_condition_compatibility
    idx = content.find('def check_plan_operation_condition_compatibility')
    if idx >= 0:
        idx2 = content.find('\ndef ', idx + 1)
        if idx2 < 0:
            idx2 = len(content)
        # Insert after the function
        new_content = content[:idx2] + new_func + content[idx2:]
        with open('app/modules/maintenance/services.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Function added successfully!")
    else:
        print("Could not find check_plan_operation_condition_compatibility")