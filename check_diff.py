with open('stage3_vs_stash_utf8.txt', 'r', encoding='utf-8') as f:
    text = f.read()

checks = [
    'managementDropdown',
    'managementBtn',
    'managementMenu',
    'menuNewOperation',
    'menuNewGroup',
    'menuEditGroup',
    'menuDeleteGroup',
    'menuRefresh',
    'models:new Set()',
    'modelsText',
    'unitText',
    'openManagementMenu',
    'managementMenu.style.left',
    '${api}/equipment/models',
]

for c in checks:
    print(f'{c}: {c in text}')