from pathlib import Path
import re
root=Path('.')
p=root/'app/modules/equipment_types/router.py';s=p.read_text(encoding='utf-8')
s=re.sub(r'(spec_definitions=services\.list_spec_definitions\(db);)+','spec_definitions=services.list_spec_definitions(db);',s,count=1)
s=re.sub(r'(specs_data=json\.loads\(specs_json\);)+','specs_data=json.loads(specs_json);',s)
p.write_text(s,encoding='utf-8')
# Ensure edit/new-model handlers carry custom spec values without adding table columns.
p=root/'app/modules/equipment_types/templates/master_data_workspace.html';h=p.read_text(encoding='utf-8')
if "renderCustomSpecs(JSON.parse(d.specs||'[]'))" not in h:
    h=h.replace("positions=JSON.parse(d.positions||'[]');sizes=JSON.parse(d.sizes||'[]');refresh();", "positions=JSON.parse(d.positions||'[]');sizes=JSON.parse(d.sizes||'[]');renderCustomSpecs(JSON.parse(d.specs||'[]'));refresh();",1)
if "positions=[];sizes=[];renderCustomSpecs([]);refresh()" not in h:
    h=h.replace("positions=[];sizes=[];refresh()", "positions=[];sizes=[];renderCustomSpecs([]);refresh()",1)
p.write_text(h,encoding='utf-8')
for q in [root/'.github/scripts/cleanup_custom_specs.py',root/'.github/scripts/cleanup_custom_specs_router.py',root/'.github/workflows/cleanup-custom-specs.yml']:
    if q.exists():q.unlink()
print('cleanup finalized')
