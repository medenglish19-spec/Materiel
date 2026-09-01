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


def _seed_equipment_classification_defaults() -> None:
    from app.modules.equipment_types.models import EquipmentCategory
    from app.database.session import SessionLocal
    defaults = (("المركبات الخفيفة", "LIGHT", 10), ("المركبات الثقيلة", "HEAVY", 20), ("معدات الأشغال", "CONSTRUCTION", 30), ("معدات الدعم", "SUPPORT", 40))
    db = SessionLocal()
    try:
        for name, code, sort_order in defaults:
            if db.query(EquipmentCategory).filter(EquipmentCategory.code == code).first() is None:
                db.add(EquipmentCategory(name=name, code=code, sort_order=sort_order, is_system=True))
        db.commit()
    finally: db.close()


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
    _seed_equipment_classification_defaults()
    from app.database.session import SessionLocal
    from app.modules.meter_readings.legacy_cleanup import cleanup_legacy_readings
    db = SessionLocal()
    try:
        removed = cleanup_legacy_readings(db)
        if removed: print(f"[init_db] تم حذف {removed} قراءة قديمة مخالفة لقواعد التاريخ/القيمة.")
    finally: db.close()


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
