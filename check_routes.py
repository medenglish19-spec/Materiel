import re

with open('app/modules/document_import/router.py', 'r', encoding='utf-8') as f:
    text = f.read()

routes = re.findall(r'@router\.(get|post|put|delete)\([\'"]([^\'"]+)', text)
for method, path in routes:
    print(f'{method}: {path}')