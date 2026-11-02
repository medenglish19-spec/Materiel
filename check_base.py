with open('base_6f2fdd89.html', 'rb') as f:
    content = f.read()
print('Length:', len(content))
if len(content) > 0:
    text = content.decode('utf-16-le')
    with open('base_6f2fdd89_utf8.html', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Written UTF-8, length:', len(text))
    checks = [
        ('models filter', 'data-filter-col="models"'),
        ('operationModels', 'operationModels'),
        ('columnFilters models', 'models:new Set()'),
        ('filterValue models', "col==='models'"),
        ('modelsText', 'modelsText'),
        ('unitText', 'unitText'),
        ('data-mt-region', 'data-mt-region'),
        ('mt-actions-th', 'mt-actions-th'),
    ]
    for name, check in checks:
        print(name + ':', check in text)
else:
    print('Empty')