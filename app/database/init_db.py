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


def _repair_existing_meter_readings_schema() -> None:
    """إصلاح أعمدة قديمة أثناء bootstrap الأول فقط قبل تثبيت Alembic."""
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "meter_readings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("meter_readings")}
    with engine.begin() as connection:
        if "updated_at" not in columns:
            connection.execute(text("ALTER TABLE meter_readings ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE meter_readings SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))
        if "equipment_status" not in columns:
            connection.execute(text("ALTER TABLE meter_readings ADD COLUMN equipment_status VARCHAR(30) NOT NULL DEFAULT 'available'"))


def _repair_existing_maintenance_schema() -> None:
    """ترحيل أعمدة legacy اللازمة فقط قبل بدء سلسلة Alembic الرسمية."""
    if not str(engine.url).startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "maintenance_records" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("maintenance_records")}
    with engine.begin() as connection:
        if "updated_at" in columns:
            connection.execute(text("ALTER TABLE maintenance_records DROP COLUMN updated_at"))
            columns.remove("updated_at")
        if "rule_id" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN rule_id INTEGER"))
            columns.add("rule_id")
        if "maintenance_date" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN maintenance_date DATE"))
            if "reported_date" in columns:
                connection.execute(text("UPDATE maintenance_records SET maintenance_date = reported_date WHERE maintenance_date IS NULL"))
            columns.add("maintenance_date")
        if "meter_value" not in columns:
            connection.execute(text("ALTER TABLE maintenance_records ADD COLUMN meter_value NUMERIC(10, 1)"))
            if "meter_reading" in columns:
                connection.execute(text("UPDATE maintenance_records SET meter_value = meter_reading WHERE meter_value IS NULL"))
            columns.add("meter_value")
