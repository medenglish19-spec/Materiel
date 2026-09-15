from pathlib import Path

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
s = s.replace("s=replace_once(s,'let positions=[], sizes=[];', 'let positions=[], sizes=[];\\nconst specDefinitions={{ spec_definitions|tojson }};", "s=replace_once(s,'let positions=[], sizes=[];', 'let positions=[], sizes=[];\\nconst specDefinitions={{ spec_definitions|tojson }};", 1) if False else s
s = s.replace("let positions=[], sizes=[];', 'let positions=[], sizes=[];\\nconst specDefinitions", "let positions=[], sizes=[];', 'let positions=[], sizes=[];\\nconst specDefinitions")
p.write_text(s, encoding="utf-8")
Path(__file__).unlink()
