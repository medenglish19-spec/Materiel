with open(r'C:\Users\utilisateur\Desktop\Materiel\app\modules\maintenance\templates\maintenance_rules_model_only.html', 'r', encoding='utf-8') as f:
    content = f.read()
for i, line in enumerate(content.split('\n'), 1):
    if 'select' in line.lower() and ('model' in line.lower() or 'id=' in line.lower()):
        # Replace non-ascii
        safe = line.encode('ascii', 'replace').decode('ascii')
        print(f'{i}: {safe}')