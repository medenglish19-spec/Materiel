# Add the missing priority_for function to services.py

with open('app/modules/maintenance/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find where to insert - after summarize_operation_conditions
insert_after = "def summarize_operation_conditions(condition_rows: list) -> dict:"

idx = content.find(insert_after)
if idx >= 0:
    # Find the end of the function
    idx2 = content.find('\ndef ', idx + 1)
    if idx2 < 0:
        idx2 = len(content)
    
    new_func = '''

def priority_for(state, remaining_meter, meta):
    if state == "مستحقة الآن":
        return 1
    if state == "تقترب":
        return 2
    if state == "بلا سجل":
        return 3
    candidates = [x for x in (remaining_meter, meta.get("remaining_days")) if x is not None]
    return 4 if candidates else 5

'''
    
    # Insert after the function
    new_content = content[:idx2] + new_func + content[idx2:]
    with open('app/modules/maintenance/services.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("priority_for function added successfully!")
else:
    print("Could not find summarize_operation_conditions")