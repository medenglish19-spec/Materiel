import sqlite3
from pathlib import Path

files = [
    "fleet_assets.db",
    "fleet_assets.db.bak-20261004-063336",
]
wanted = ["equipment", "equipment_models", "equipment_types"]

for name in files:
    p = Path(name)
    print("\n==========", name, "==========")
    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    for table in wanted:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
        if not exists:
            continue

        columns = [
            row["name"]
            for row in con.execute(f'PRAGMA table_info("{table}")')
        ]
        print(f"\n--- {table} | الأعمدة: {columns} ---")

        rows = con.execute(f'SELECT * FROM "{table}" LIMIT 10').fetchall()
        for row in rows:
            print(dict(row))

    con.close()
