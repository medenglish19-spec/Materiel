from pathlib import Path
import re

p = Path(__file__).with_name("apply_custom_specs.py")
s = p.read_text(encoding="utf-8")
start = s.index("# Add axle upper-bound validation")
end = s.index("# Inject sync before final commit")
replacement = "# Add axle upper-bound validation inside the tire-position validator.\n"
replacement += 'match = re.search(r"(def _validate_tire_positions_and_sizes\\(.*?\\n\\s*if data\\.has_tires:\\n)", s, re.S)\n'
replacement += 'if not match: raise SystemExit("missing tire-position validator in service source")\n'
replacement += 'addition = "        if data.axle_count is not None:\\n            invalid=[p.axle_number for p in data.positions if p.axle_number>data.axle_count]\\n            if invalid: raise ValueError(f\\"رقم المحور {max(invalid)} يتجاوز عدد محاور الطراز المحدد ({data.axle_count})\\")\\n"\n'
replacement += 's=s[:match.end()]+addition+s[match.end():]\n'
s = s[:start] + replacement + s[end:]
p.write_text(s, encoding="utf-8")
Path(__file__).unlink()
