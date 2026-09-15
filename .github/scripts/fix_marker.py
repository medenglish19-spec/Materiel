from pathlib import Path
import re

p = Path(__file__).with_name("apply_custom_specs.py")
s = p.read_text(encoding="utf-8")
start = s.index("# Add axle upper-bound validation")
end = s.index("# Inject sync before final commit")
match = re.search(r"([^\\n]*توجد مواضع إطارات مكررة[^\\n]*\\n)", s)
if not match:
    raise SystemExit("missing duplicate-position validation in service source")
replacement = '''# Add axle upper-bound validation after the existing duplicate-position check.
match = re.search(r"([^\\n]*توجد مواضع إطارات مكررة[^\\n]*\\n)", s)
if not match:
    raise SystemExit("missing duplicate-position validation in service source")
addition = '''        if data.axle_count is not None:
            invalid=[p.axle_number for p in data.positions if p.axle_number>data.axle_count]
            if invalid: raise ValueError(f"رقم المحور {max(invalid)} يتجاوز عدد محاور الطراز المحدد ({data.axle_count})")
'''
s = s[:start] + replacement + "s=s[:match.end()]+addition+s[match.end():]\\n" + s[end:]
p.write_text(s, encoding="utf-8")
Path(__file__).unlink()
