from pathlib import Path
import re
root=Path('.')
# router: remove duplicate spec definition lookup and duplicate specs_json parsing
p=root/'app/modules/equipment_types/router.py';s=p.read_text(encoding='utf-8')
s=re.sub(r'(models=services\.list_models\(db\);tire_master_data=\{\};spec_definitions=services\.list_spec_definitions\(db\);)spec_definitions=services\.list_spec_definitions\(db\);+',r'\1',s)
s=re.sub(r'(specs_data=json\.loads\(specs_json\);)specs_data=json\.loads\(specs_json\);+',r'\1',s)
p.write_text(s,encoding='utf-8')
# master data: add custom-spec chips to model rows, no new columns; show only entered values
p=root/'app/modules/equipment_types/templates/master_data_workspace.html';h=p.read_text(encoding='utf-8')
old='<td>{{ \'نعم\' if model.has_tires else \'لا\' }}</td><td><button type="button" class="edit-model"'
new='<td>{{ \'نعم\' if model.has_tires else \'لا\' }}</td><td>{% for spec in model.spec_values %}<span class="chip">{{ spec.definition.name }}: {{ spec.value }}{% if spec.definition.unit %} {{ spec.definition.unit }}{% endif %}</span>{% endfor %}<button type="button" class="edit-model"'
if old in h:
    h=h.replace(old,new,1)
    h=h.replace('<th>الإطارات</th><th>إجراء</th>','<th>الإطارات</th><th>الخصائص</th><th>إجراء</th>',1)
    h=h.replace('<tr><td colspan="5">لا توجد طرازات.</td>','<tr><td colspan="6">لا توجد طرازات.</td>',1)
p.write_text(h,encoding='utf-8')
print('cleanup applied')
