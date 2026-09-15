from pathlib import Path
import re
p=Path('app/modules/equipment_types/router.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'(spec_definitions=services\.list_spec_definitions\(db\);)+','spec_definitions=services.list_spec_definitions(db);',s,count=1)
s=re.sub(r'(specs_data=json\.loads\(specs_json\);)+','specs_data=json.loads(specs_json);',s)
p.write_text(s,encoding='utf-8')
Path(__file__).unlink()
