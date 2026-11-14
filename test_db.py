import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.database.session import SessionLocal
from app.modules.maintenance.models import MaintenanceOperation, MaintenanceOperationGroup

db = SessionLocal()
ops = db.query(MaintenanceOperation).all()
print(f"Operations: {len(ops)}")
ops_with_models = [op for op in ops if op.equipment_models]
ops_without_models = [op for op in ops if not op.equipment_models]
print(f"Operations WITH models: {len(ops_with_models)}")
print(f"Operations WITHOUT models: {len(ops_without_models)}")
for op in ops_with_models[:20]:
    model_ids = [m.id for m in op.equipment_models]
    print(f"  - {op.id}: {op.name}, models: {model_ids}")
db.close()