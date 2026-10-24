with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

print('managementDropdown:', 'managementDropdown' in text)
print('class="dropdown":', 'class="dropdown"' in text)
print('managementBtn:', 'managementBtn' in text)
print('managementMenu:', 'managementMenu' in text)
print('managementMenu (style):', 'managementMenu' in text and 'position:fixed' in text)