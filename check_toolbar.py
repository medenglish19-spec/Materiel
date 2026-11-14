with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Find the toolbar section
idx = text.find('toolbar-card')
if idx != -1:
    print('toolbar-card found at:', idx)
    print(text[idx:idx+500])
else:
    print('toolbar-card NOT found')