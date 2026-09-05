from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from app.core.config import settings
from app.database.base import Base
from app.database.session import engine
from app.modules.meter_readings import models as meter_models  # noqa: F401
from app.modules.meter_readings import batches as meter_batches  # noqa: F401
from app.modules.meter_readings import audit as meter_audit  # noqa: F401
from app.modules.meter_readings import audit_events as meter_audit_events  # noqa: F401
from app.modules.users import models as users_models  # noqa: F401
from app.modules.equipment_types import models as equipment_types_models  # noqa: F401
from app.modules.equipment import models as equipment_models  # noqa: F401
from app.modules.meter_readings import models as meter_readings_models  # noqa: F401
from app.modules.maintenance import models as maintenance_models  # noqa: F401
from app.modules.faults_repairs import models as faults_repairs_models  # noqa: F401
from app.modules.tires import models as tires_models  # noqa: F401
from app.modules.batteries import models as batteries_models  # noqa: F401
from app.modules.fuel import models as fuel_models  # noqa: F401
from app.modules.missions import models as missions_models  # noqa: F401


def _repair_existing_meter_readings_schema() -> None:
    if not str(engine.url).startswith("sqlite"): return
    inspector = inspect(engine)
    if "meter_readings" not in inspector.get_table_names(): return
    columns = {column["name"] for column in inspector.get_columns("meter_readings")}
    with engine.begin() as connection:
        if "updated_at" not in columns:
            connection.execute(text("ALTER TABLE meter_readings ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE meter_readings SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))
        if "equipment_status" not in columns:
            connection.execute(text("ALTER TABLE meter_readings ADD COLUMN equipment_status VARCHAR(30) NOT NULL DEFAULT 'available'"))


def _repair_existing_maintenance_schema() -> None:
    if not str(engine.url).startswith("sqlite"): return
    inspector = inspect(engine)
    if "maintenance_records" not in inspector.get_table_names(): return
    columns = {column["name"] for column in inspector.get_columns("maintenance_records")}
    with engine.begin() as connection:
        if "updated_at" in columns:
            connection.execute(text("ALTER TABLE maintenance_records DROP COLUMN updated_at")); columns.remove("updated_at")
        if "rule_id" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN rule_id INTEGER")); columns.add("rule_id")
        if "maintenance_date" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN maintenance_date DATE"))
            if "reported_date" in columns: connection.execute(text("UPDATE maintenance_records SET maintenance_date = reported_date WHERE maintenance_date IS NULL"))
            columns.add("maintenance_date")
        if "meter_value" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN meter_value NUMERIC(10, 1)"))
            if "meter_reading" in columns: connection.execute(text("UPDATE maintenance_records SET meter_value = meter_reading WHERE meter_value IS NULL"))
            columns.add("meter_value")
        if "work_order" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN work_order VARCHAR(80)")); columns.add("work_order")
        if "workshop" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN workshop VARCHAR(120)"))
            if "location" in columns: connection.execute(text("UPDATE maintenance_records SET workshop = location WHERE workshop IS NULL"))
            columns.add("workshop")
        if "status" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'completed'")); columns.add("status")
        if "is_scheduled" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN is_scheduled BOOLEAN NOT NULL DEFAULT 0")); columns.add("is_scheduled")
        if "description" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN description TEXT")); columns.add("description")
        if "created_at" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN created_at DATETIME"))
            connection.execute(text("UPDATE maintenance_records SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")); columns.add("created_at")
        if "reported_date" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN reported_date DATE")); columns.add("reported_date")
        connection.execute(text("UPDATE maintenance_records SET maintenance_date = COALESCE(maintenance_date, reported_date, DATE(created_at), DATE('now')) WHERE maintenance_date IS NULL"))
        connection.execute(text("UPDATE maintenance_records SET reported_date = COALESCE(reported_date, maintenance_date, DATE(created_at), DATE('now')) WHERE reported_date IS NULL"))


def _repair_equipment_current_meters() -> None:
    """Reconcile stored current meters with the newest maintenance/meter observation.

    This is intentionally idempotent and runs at startup so older data such as a
    current odometer of 500 with a later maintenance meter of 581 is corrected
    without requiring the user to edit the old record manually.
    """
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType
    from app.modules.meter_readings.models import MeterReading
    from app.modules.maintenance.models import MaintenanceRecord
    from app.database.session import SessionLocal

    db = SessionLocal()
    try:
        equipment_list = db.query(Equipment).join(EquipmentType, Equipment.equipment_type_id == EquipmentType.id).all()
        changed = 0
        for equipment in equipment_list:
            unit = (equipment.equipment_type.measurement_unit or "").strip().lower()
            if unit not in ("km", "hours"):
                continue
            if unit == "km":
                latest_reading = db.query(MeterReading).filter(
                    MeterReading.equipment_id == equipment.id,
                    MeterReading.odometer.is_not(None),
                ).order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()
            else:
                latest_reading = db.query(MeterReading).filter(
                    MeterReading.equipment_id == equipment.id,
                    MeterReading.hours.is_not(None),
                ).order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()
            latest_maintenance = db.query(MaintenanceRecord).filter(
                MaintenanceRecord.equipment_id == equipment.id,
                MaintenanceRecord.meter_value.is_not(None),
            ).order_by(MaintenanceRecord.maintenance_date.desc(), MaintenanceRecord.id.desc()).first()

            candidates = []
            if latest_reading is not None:
                value = latest_reading.odometer if unit == "km" else latest_reading.hours
                candidates.append((latest_reading.reading_date.date(), value) if hasattr(latest_reading.reading_date, "date") else (latest_reading.reading_date, value))
            if latest_maintenance is not None:
                candidates.append((latest_maintenance.maintenance_date, latest_maintenance.meter_value))
            if not candidates:
                continue
            latest_date = max(item[0] for item in candidates)
            current_value = max(item[1] for item in candidates if item[0] == latest_date)
            current_value = float(current_value) if current_value is not None else None
            if current_value is None:
                continue
            if unit == "km":
                old_value = float(equipment.current_odometer) if equipment.current_odometer is not None else None
                if old_value != current_value:
                    equipment.current_odometer = current_value
                    changed += 1
            else:
                old_value = float(equipment.current_hours) if equipment.current_hours is not None else None
                if old_value != current_value:
                    equipment.current_hours = current_value
                    changed += 1
        if changed:
            db.commit()
            print(f"[init_db] تمت مزامنة العداد الحالي لـ {changed} عتاد/مركبة.")
    finally:
        db.close()


def _normalize_equipment_classification_defaults() -> None:
    """Remove unused built-in categories so classification is fully user-defined.

    If an old built-in category is already used by real types, keep it as a normal
    user category instead of changing or deleting existing classification data.
    """
    from app.modules.equipment_types.models import EquipmentCategory, EquipmentType
    from app.database.session import SessionLocal

    default_codes = {"LIGHT", "HEAVY", "CONSTRUCTION", "SUPPORT"}
    db = SessionLocal()
    try:
        categories = db.query(EquipmentCategory).filter(EquipmentCategory.code.in_(default_codes)).all()
        changed = False
        for category in categories:
            linked = db.query(EquipmentType).filter(EquipmentType.category_id == category.id).first()
            if linked is None:
                db.delete(category)
            elif category.is_system:
                category.is_system = False
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL).replace("%", "%%"))
    return config


def _has_current_classification_schema(tables: set[str]) -> bool:
    if not {"equipment_categories", "equipment_brands"}.issubset(tables): return False
    inspector = inspect(engine)
    type_columns = {c["name"] for c in inspector.get_columns("equipment_types")}
    model_columns = {c["name"] for c in inspector.get_columns("equipment_models")}
    return "category_id" in type_columns and "brand_id" in model_columns


def _has_model_exception_schema() -> bool:
    inspector = inspect(engine)
    if "maintenance_rules" not in inspector.get_table_names(): return False
    columns = {c["name"] for c in inspector.get_columns("maintenance_rules")}
    return {"equipment_model_id", "parent_rule_id"}.issubset(columns)


def init_db() -> None:
    inspector = inspect(engine); tables = set(inspector.get_table_names()); config = _alembic_config()
    if "alembic_version" not in tables:
        if not tables:
            Base.metadata.create_all(bind=engine); command.stamp(config, "head")
        else:
            _repair_existing_meter_readings_schema(); _repair_existing_maintenance_schema(); command.stamp(config, "0001_baseline"); command.upgrade(config, "head")
    else: command.upgrade(config, "head")
    _normalize_equipment_classification_defaults()
    from app.database.session import SessionLocal
    from app.modules.meter_readings.legacy_cleanup import cleanup_legacy_readings
    db = SessionLocal()
    try:
        removed = cleanup_legacy_readings(db)
        if removed: print(f"[init_db] تم حذف {removed} قراءة قديمة مخالفة لقواعد التاريخ/القيمة.")
    finally: db.close()
    _repair_equipment_current_meters()


def create_default_admin() -> None:
    from app.database.session import SessionLocal
    from app.modules.users.services import get_user_by_username, create_user
    from app.modules.users.schemas import UserCreate
    db = SessionLocal()
    try:
        existing = get_user_by_username(db, "admin")
        if not existing:
            create_user(db, UserCreate(username="admin", full_name="مدير النظام", password="Admin@123", role="admin"))
            print("[init_db] تم إنشاء مستخدم افتراضي: admin / Admin@123")
    finally: db.close()
