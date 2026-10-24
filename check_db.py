import sqlite3
c = sqlite3.connect('fleet_assets.db')
print('=== maintenance_operation_models ===')
for r in c.execute('SELECT * FROM maintenance_operation_models'):
    print(r)
print()
print('=== Tables ===')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'maintenance_%'"):
    print(r[0])