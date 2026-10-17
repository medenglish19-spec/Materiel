with open('head_template.txt', 'rb') as f:
    content = f.read()
text = content.decode('utf-8')
print('HEAD version length:', len(text))
checks = [
    ('managementDropdown', 'managementDropdown'),
    ('managementBtn', 'managementBtn'),
    ('managementMenu', 'managementMenu'),
    ('data-filter-col=models', 'data-filter-col="models"'),
    ('operationModels', 'operationModels'),
    ('menuNewOperation', 'menuNewOperation'),
    ('columnFilters models', 'models:new Set()'),
]
for name, check in checks:
    found = check in text
    print(name + ':', found)