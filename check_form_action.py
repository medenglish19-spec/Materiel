import re

with open('app/modules/document_import/templates/upload.html', 'r', encoding='utf-8') as f:
    text = f.read()

actions = re.findall(r'action=[\'"]([^\'"]+)', text)
for a in actions:
    print(a)