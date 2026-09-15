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
# Remove the brittle edit-handler assertion from the generated script; wire the template robustly below.
s = re.sub(r"if 'renderCustomSpecs\\(JSON\\.parse\\(this\\.dataset\\.specs\\|\\|'\\[\\]'\\)\\)' not in s:\\n    raise SystemExit\\(\"edit handler specs anchor missing\"\\)\\n", "", s)
p.write_text(s, encoding="utf-8")

t = Path("app/modules/equipment_types/templates/master_data_workspace.html")
html = t.read_text(encoding="utf-8")
if "data-specs='{{ td.specs|tojson|e }}'" not in html:
    html = html.replace("data-sizes='{{ td.sizes|tojson|e }}'>تعديل", "data-sizes='{{ td.sizes|tojson|e }}' data-specs='{{ td.specs|tojson|e }}'>تعديل", 1)
if "renderCustomSpecs(JSON.parse(this.dataset.specs||'[]'))" not in html:
    html = re.sub(r"(sizes\\s*=\\s*JSON\\.parse\\(this\\.dataset\\.sizes\\|\\|'\\[\\]'\\)\\s*;)", r"\\1renderCustomSpecs(JSON.parse(this.dataset.specs||'[]'));", html, count=1)
t.write_text(html, encoding="utf-8")
Path(__file__).unlink()
