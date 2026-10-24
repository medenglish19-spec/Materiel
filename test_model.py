import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database.session import SessionLocal
from app.modules.maintenance.models import MaintenanceOperation, MaintenanceOperationGroup
from app.modules.equipment_types.models import EquipmentModel

db = SessionLocal()
ops = db.query(MaintenanceOperation).all()
models = db.query(EquipmentModel).all()

print(f"Operations: {len(ops)}")
print(f"Equipment models: {len(models)}")
for m in models[:10]:
    print(f"  - Model {m.id}: {m.name}")

# Check if any operations have model associations
ops_with_models = [op for op in ops if op.equipment_models]
print(f"Operations WITH models: {len(ops_with_models)}")
for op in ops_with_models:
    print(f"  - Op {op.id}: {op.name}, models: {[m.id for m in op.equipment_models]}")

db.close()