with open('base_6f2fdd89_utf8.html', 'r', encoding='utf-8') as f:
    text = f.read()

checks = [
    ('managementDropdown', 'managementDropdown'),
    ('managementBtn', 'managementBtn'),
    ('managementMenu', 'managementMenu'),
    ('menuNewOperation', 'menuNewOperation'),
    ('menuNewGroup', 'menuNewGroup'),
    ('menuEditGroup', 'menuEditGroup'),
    ('menuDeleteGroup', 'menuDeleteGroup'),
    ('menuRefresh', 'menuRefresh'),
    ('models:new Set()', 'models:new Set()'),
    ('modelsText', 'modelsText'),
    ('unitText', 'unitText'),
    ('col models', 'col==="models"'),
    ('data-mt-region', 'data-mt-region'),
    ('mt-actions-th', 'mt-actions-th'),
    ('operationModels', 'operationModels'),
    ('data-filter-col models', 'data-filter-col="models"'),
]

for name, c in checks:
    print(name + ':', c in text)