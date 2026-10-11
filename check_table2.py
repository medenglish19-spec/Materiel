with open('app/modules/maintenance/templates/maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('table-wrap')
context = text[max(0,idx-50):idx+100]
with open('table_context.txt', 'w', encoding='utf-8') as f:
    f.write(context)
print('Written')