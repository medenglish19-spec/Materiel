with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('toolbar-card')
if idx != -1:
    with open('current_toolbar.txt', 'w', encoding='utf-8') as f:
        f.write(text[idx:idx+800])
    print('Written')
else:
    print('NOT found')