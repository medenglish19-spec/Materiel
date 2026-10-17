from app.database.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
# Check if we can manually add the columns
try:
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN condition_source TEXT NOT NULL DEFAULT 'unset'"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN interval_km NUMERIC(10,1)"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN interval_hours NUMERIC(10,1)"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN interval_days INTEGER"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN warning_km NUMERIC(10,1)"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN warning_days INTEGER"))
    db.execute(text("ALTER TABLE maintenance_operation_models ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"))
    db.commit()
    print("Columns added successfully")
except Exception as e:
    print(f"Error: {e}")
    db.rollback()

# Verify
from sqlalchemy import inspect
insp = inspect(db.bind)
cols = insp.get_columns("maintenance_operation_models")
for col in cols:
    print(col)
db.close()