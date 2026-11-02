with open('web/main.py', 'r', encoding='utf-8') as f:
    text = f.read()

old = '    app.include_router(fuel_router, tags=["fuel"])\n    app.include_router(missions_router, tags=["missions"])'
new = '    app.include_router(fuel_router, tags=["fuel"])\n    app.include_router(document_import_router, tags=["document_import"])\n    app.include_router(missions_router, tags=["missions"])'

text = text.replace(old, new)

with open('web/main.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Fixed')