# Add the missing operation_condition_meta function to services.py

with open('app/modules/maintenance/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where to insert - after status_for function
insert_after = "def status_for(condition, equipment, record, current_value, plan_operation=None, today=None):"

idx = content.find(insert_after)
if idx >= 0:
    # Find the end of the function
    idx2 = content.find('\ndef ', idx + 1)
    if idx2 < 0:
        idx2 = len(content)
    
    new_func = '''

def operation_condition_meta(condition, equipment, record, current_value, today=None):
    """Due state of one operation under one model's condition.

    The engine refuses to invent a condition: an unset or interval-less model
    condition yields an explicit "not computed" state. The operation's legacy
    shared columns are never consulted, so they cannot produce a due state.
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
    return status_for(condition, equipment, record, current_value, today=today)

'''
    
    # Insert after the function
    new_content = content[:idx2] + new_func + content[idx2:]
    with open('app/modules/maintenance/services.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("operation_condition_meta function added successfully!")
else:
    print("Could not find status_for function")