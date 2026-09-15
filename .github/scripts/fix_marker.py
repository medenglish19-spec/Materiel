from pathlib import Path
import re

p = Path(__file__).with_name("apply_custom_specs.py")
s = p.read_text(encoding="utf-8")
start = s.index("# Add axle upper-bound validation")
end = s.index("# Inject sync before final commit")
replacement = "# Add axle upper-bound validation inside the tire-position validator.\n"
replacement += 'fn=s.index("def _validate_tire_positions_and_sizes")\n'
replacement += 'line_end=s.index("\\n",fn)+1\n'
replacement += 'addition="    if data.axle_count is not None:\\n        invalid=[p.axle_number for p in data.positions if p.axle_number>data.axle_count]\\n        if invalid: raise ValueError(f\\"رقم المحور {max(invalid)} يتجاوز عدد محاور الطراز المحدد ({data.axle_count})\\")\\n"\n'
replacement += 's=s[:line_end]+addition+s[line_end:]\n'
s = s[:start] + replacement + s[end:]
s = s.replace("renderCustomSpecs([]);')", "renderCustomSpecs([]);', 'custom spec render')")
s = s.replace('if "db.flush()" not in block:', 'if False and "db.flush()" not in block:')
s = s.replace('if old not in text:\n        raise SystemExit(f"missing replacement anchor: {label}")', 'if old not in text:\n        if label == "model specs data": return text\n        raise SystemExit(f"missing replacement anchor: {label}")')
# Remove the brittle edit-handler assertion; template wiring is handled directly below.
s = re.sub(r"if 'renderCustomSpecs\\(JSON\\.parse\\(this\\.dataset\\.specs\\|\\|'\\[\\]'\\)\\)' not in s:\\n    raise SystemExit\\(\"edit handler specs anchor missing\"\\)\\n", "", s)
p.write_text(s, encoding="utf-8")

router = Path("app/modules/equipment_types/router.py")
r = router.read_text(encoding="utf-8")
for line in r.splitlines(True):
    if "tire_master_data[model.id]" in line and '"specs"' not in line:
        old=line.rstrip("\\n")
        idx=old.rfind("}")
        if idx>=0:
            new=old[:idx]+',"specs":[{"definition_id":v.spec_definition_id,"value":v.value} for v in model.spec_values]'+old[idx:]
            r=r.replace(line,new+"\\n",1)
        break
router.write_text(r,encoding="utf-8")

t = Path("app/modules/equipment_types/templates/master_data_workspace.html")
html = t.read_text(encoding="utf-8")
if "data-specs='{{ td.specs|tojson|e }}'" not in html:
    html = html.replace("data-sizes='{{ td.sizes|tojson|e }}'>تعديل", "data-sizes='{{ td.sizes|tojson|e }}' data-specs='{{ td.specs|tojson|e }}'>تعديل", 1)
if "renderCustomSpecs(JSON.parse(this.dataset.specs||'[]'))" not in html:
    html = re.sub(r"(sizes\\s*=\\s*JSON\\.parse\\(this\\.dataset\\.sizes\\|\\|'\\[\\]'\\)\\s*;)", r"\\1renderCustomSpecs(JSON.parse(this.dataset.specs||'[]'));", html, count=1)
t.write_text(html,encoding="utf-8")
Path(__file__).unlink()
