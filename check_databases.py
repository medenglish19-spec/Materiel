import sqlite3
from pathlib import Path
from datetime import datetime

for name in ("fleet_assets.db", "fleet_assets.db.bak-20261004-063336"):
    p = Path(name)
    print("\n===", name, "===")

    if not p.exists():
        print("غير موجود")
        continue

    print("الحجم:", p.stat().st_size)
    print("آخر تعديل:", datetime.fromtimestamp(p.stat().st_mtime))

    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    tables = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    for (table,) in tables:
        if any(word in table.lower() for word in ("equipment", "asset", "model", "spec")):
            safe_table = table.replace('"', '""')
            count = con.execute(
                'SELECT COUNT(*) FROM "' + safe_table + '"'
            ).fetchone()[0]
            print(table, "=", count)

    con.close()
