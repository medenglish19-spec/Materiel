with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with operations_payload,
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if 'operations_payload,' in line and 'operations_payload_list' not in ''.join(lines[max(0,i-5):i+5]):
        # Add the new import after this line
        new_lines.append('    operations_payload_list,\n')

with open('app/modules/maintenance/router.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Done!")