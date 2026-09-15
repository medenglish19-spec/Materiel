from pathlib import Path
p=Path('app/modules/equipment_types/router.py')
s=p.read_text(encoding='utf-8')
s=s.replace('spec_definitions=services.list_spec_definitions(db);spec_definitions=services.list_spec_definitions(db)','spec_definitions=services.list_spec_definitions(db)')
s=s.replace('specs_data=json.loads(specs_json);specs_data=json.loads(specs_json)','specs_data=json.loads(specs_json)')
p.write_text(s,encoding='utf-8')
