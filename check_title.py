with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('block title')
if idx != -1:
    with open('title_section.txt', 'w', encoding='utf-8') as f:
        f.write(text[idx:idx+200])
    print('Written')
else:
    print('block title not found')