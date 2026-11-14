with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('table-wrap')
if idx != -1:
    with open('table_wrap_full.txt', 'w', encoding='utf-8') as f:
        f.write(text[max(0, idx-100):idx+200])
    print('Written')
else:
    print('NOT found')