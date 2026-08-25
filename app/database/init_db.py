from sqlalchemy import inspect, text

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


def _repair_existing_meter_readings_schema() -> None:
    """إصلاح أعمدة أضيفت في الإصدارات الجديدة عند استخدام SQLite."""
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "meter_readings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("meter_readings")}
    with engine.begin() as connection:
        if "updated_at" not in columns:
            connection.execute(text("ALTER TABLE meter_readings ADD COLUMN updated_at DATETIME"))
            connection.execute(text(
                "UPDATE meter_readings SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
                "WHERE updated_at IS NULL"
            ))
        if "equipment_status" not in columns:
            connection.execute(text(
                "ALTER TABLE meter_readings ADD COLUMN equipment_status VARCHAR(30) NOT NULL DEFAULT 'available'"
            ))


def _repair_existing_maintenance_schema() -> None:
    """ترحيل آمن لجدول سجلات الصيانة القديم إلى مخطط الوحدة الحالية دون حذف البيانات."""
    if not str(engine.url).startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "maintenance_records" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("maintenance_records")}
    with engine.begin() as connection:
        if "rule_id" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN rule_id INTEGER"))

        if "maintenance_date" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN maintenance_date DATE"))
            if "reported_date" in columns:
                connection.execute(text(
                    "UPDATE maintenance_records "
                    "SET maintenance_date = reported_date "
                    "WHERE maintenance_date IS NULL"
                ))

        if "meter_value" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN meter_value NUMERIC(10, 1)"))
            if "meter_reading" in columns:
                connection.execute(text(
                    "UPDATE maintenance_records "
                    "SET meter_value = meter_reading "
                    "WHERE meter_value IS NULL"
                ))

        if "work_order" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN work_order VARCHAR(80)"))

        if "workshop" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN workshop VARCHAR(120)"))
            if "location" in columns:
                connection.execute(text(
                    "UPDATE maintenance_records "
                    "SET workshop = location "
                    "WHERE workshop IS NULL"
                ))

        if "status" not in columns:
            connection.execute(text(
                "ALTER TABLE maintenance_records ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'completed'"
            ))

        if "is_scheduled" not in columns:
            connection.execute(text(
                "ALTER TABLE maintenance_records ADD COLUMN is_scheduled BOOLEAN NOT NULL DEFAULT 0"
            ))

        if "description" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN description TEXT"))

        if "created_at" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN created_at DATETIME"))
            connection.execute(text(
                "UPDATE maintenance_records SET created_at = CURRENT_TIMESTAMP "
                "WHERE created_at IS NULL"
            ))

        if "reported_date" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN reported_date DATE"))

        connection.execute(text(
            "UPDATE maintenance_records "
            "SET maintenance_date = COALESCE(maintenance_date, reported_date, DATE(created_at), DATE('now')) "
            "WHERE maintenance_date IS NULL"
        ))
        connection.execute(text(
            "UPDATE maintenance_records "
            "SET reported_date = COALESCE(reported_date, maintenance_date, DATE(created_at), DATE('now')) "
            "WHERE reported_date IS NULL"
        ))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _repair_existing_meter_readings_schema()
    _repair_existing_maintenance_schema()
    from app.database.session import SessionLocal
    from app.modules.meter_readings.legacy_cleanup import cleanup_legacy_readings

    db = SessionLocal()
    try:
        removed = cleanup_legacy_readings(db)
        if removed:
            print(f"[init_db] تم حذف {removed} قراءة قديمة مخالفة لقواعد التاريخ/القيمة.")
    finally:
        db.close()


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
    finally:
        db.close()
