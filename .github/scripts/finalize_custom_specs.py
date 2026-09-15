from pathlib import Path
import re

root=Path('.')
router=root/'app/modules/equipment_types/router.py'
r=router.read_text(encoding='utf-8')
# Deduplicate repeated schema imports introduced during the iterative patching pass.
line=next((x for x in r.splitlines() if x.startswith('from app.modules.equipment_types.schemas import ')),None)
if line:
    names=line.split(' import ',1)[1].split(', ')
    unique=[]
    for n in names:
        if n not in unique: unique.append(n)
    newline='from app.modules.equipment_types.schemas import '+', '.join(unique)
    r=re.sub(r'^from app\.modules\.equipment_types\.schemas import .*$',newline,r,count=1,flags=re.M)
# Collapse repeated spec-definition lookup and repeated JSON parsing.
r=re.sub(r'(models=services\.list_models\(db\);tire_master_data=\{\};spec_definitions=services\.list_spec_definitions\(db\);)spec_definitions=services\.list_spec_definitions\(db\);+',r'\1',r)
r=re.sub(r'(specs_data=json\.loads\(specs_json\);)(specs_data=json\.loads\(specs_json\);)+',r'\1',r)
# Replace the model payload line with a deterministic payload including custom specs.
pattern=r'^\s*tire_master_data\[model\.id\]=.*$'
clean='''        tire_master_data[model.id]={"positions":[{"id":p.id,"axle_number":p.axle_number,"side":p.side,"position_type":p.position_type,"description":p.description} for p in db.query(TirePosition).filter(TirePosition.equipment_model_id==model.id).order_by(TirePosition.axle_number,TirePosition.sort_order,TirePosition.id).all()],"sizes":[row.size for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==model.id).order_by(TireModelSize.id).all()],"specs":[{"definition_id":v.spec_definition_id,"value":v.value} for v in model.spec_values]}'''
r=re.sub(pattern,clean,r,count=1,flags=re.M)
router.write_text(r,encoding='utf-8')

t=root/'app/modules/equipment_types/templates/master_data_workspace.html'
h=t.read_text(encoding='utf-8')
# Load current custom values when editing and clear them for a new model.
if "renderCustomSpecs(JSON.parse(d.specs||'[]'))" not in h:
    h=h.replace("positions=JSON.parse(d.positions||'[]');sizes=JSON.parse(d.sizes||'[]');refresh();", "positions=JSON.parse(d.positions||'[]');sizes=JSON.parse(d.sizes||'[]');renderCustomSpecs(JSON.parse(d.specs||'[]'));refresh();",1)
if "renderCustomSpecs([]);refresh()" not in h:
    h=h.replace("positions=[];sizes=[];refresh()", "positions=[];sizes=[];renderCustomSpecs([]);refresh()",1)
# Make the select-options field conditional.
if 'id="specDataType"' not in h:
    h=h.replace('<select name="data_type"><option value="text">نص</option>', '<select name="data_type" id="specDataType"><option value="text">نص</option>',1)
if "specDataType" in h and "specOptionsField" not in h:
    h=h.replace('<label>القيم المسموحة<input name="options"></label>', '<label id="specOptionsField" style="display:none">القيم المسموحة<input name="options"></label>',1)
if "document.getElementById('specDataType')?.addEventListener" not in h:
    h=h.replace('</script>\n</div>{% endblock %}', "document.getElementById('specDataType')?.addEventListener('change',function(){document.getElementById('specOptionsField').style.display=this.value==='select'?'flex':'none'});\n</script>\n</div>{% endblock %}",1)
t.write_text(h,encoding='utf-8')

# Remove all temporary implementation machinery from the final branch.
for path in [root/'.github/workflows/apply-custom-specs.yml',root/'.github/scripts/apply_custom_specs.py',root/'.github/scripts/apply_custom_specs_v2.py',root/'.github/scripts/fix_marker.py',root/'.github/scripts/finalize_custom_specs.py']:
    if path.exists(): path.unlink()
print('finalized custom specs')
