"""Remove duplicated meter values from domain tables.

Revision ID: centralize_meter_values_only
Revises: unify_module_meter_readings_20261014
"""
from alembic import op
import sqlalchemy as sa


revision = "centralize_meter_values_only"
down_revision = "unify_module_meter_readings_20261014"
branch_labels = None
depends_on = None


def _drop_column(table: str, column: str, constraints: tuple[str, ...] = ()):
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    columns = {item["name"] for item in inspector.get_columns(table)}
    existing_constraints = {item.get("name") for item in inspector.get_check_constraints(table)}
    if column not in columns and not (set(constraints) & existing_constraints):
        return
    with op.batch_alter_table(table) as batch:
        for constraint in constraints:
            if constraint in existing_constraints:
                batch.drop_constraint(constraint, type_="check")
        if column in columns:
            batch.drop_column(column)


def _create_sqlite_meter_triggers():
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute("""
        CREATE TRIGGER trg_meter_readings_validate_insert
        BEFORE INSERT ON meter_readings
        BEGIN
            SELECT CASE WHEN date(NEW.reading_date) > date('now')
                THEN RAISE(ABORT, 'لا يمكن إدخال قراءة بتاريخ مستقبلي') END;
            SELECT CASE WHEN NEW.odometer < 0 OR NEW.hours < 0
                THEN RAISE(ABORT, 'قيمة العداد لا يمكن أن تكون سالبة') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM equipment e JOIN equipment_types t ON t.id=e.equipment_type_id
                WHERE e.id=NEW.equipment_id AND t.measurement_unit IN ('km','hours')
                  AND ((t.measurement_unit='km' AND NEW.odometer IS NOT NULL AND NEW.hours IS NULL)
                    OR (t.measurement_unit='hours' AND NEW.hours IS NOT NULL AND NEW.odometer IS NULL))
            ) THEN RAISE(ABORT, 'وحدة قراءة العداد لا تطابق وحدة العتاد') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM meter_readings r
                WHERE r.equipment_id=NEW.equipment_id
                  AND date(r.reading_date)=date(NEW.reading_date)
            ) THEN RAISE(ABORT, 'توجد قراءة مسجلة لهذا العتاد في التاريخ نفسه') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM meter_readings r
                WHERE r.equipment_id=NEW.equipment_id
                  AND ((NEW.odometer IS NOT NULL AND r.odometer IS NOT NULL AND
                        ((date(r.reading_date)<date(NEW.reading_date) AND r.odometer>NEW.odometer)
                         OR (date(r.reading_date)>date(NEW.reading_date) AND r.odometer<NEW.odometer)))
                    OR (NEW.hours IS NOT NULL AND r.hours IS NOT NULL AND
                        ((date(r.reading_date)<date(NEW.reading_date) AND r.hours>NEW.hours)
                         OR (date(r.reading_date)>date(NEW.reading_date) AND r.hours<NEW.hours))))
            ) THEN RAISE(ABORT, 'تسلسل قراءة العداد يتعارض مع السجل المركزي') END;
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_meter_readings_validate_update
        BEFORE UPDATE OF equipment_id, reading_date, odometer, hours ON meter_readings
        BEGIN
            SELECT CASE WHEN date(NEW.reading_date) > date('now')
                THEN RAISE(ABORT, 'لا يمكن تعديل قراءة إلى تاريخ مستقبلي') END;
            SELECT CASE WHEN NEW.odometer < 0 OR NEW.hours < 0
                THEN RAISE(ABORT, 'قيمة العداد لا يمكن أن تكون سالبة') END;
            SELECT CASE WHEN NOT EXISTS (
                SELECT 1 FROM equipment e JOIN equipment_types t ON t.id=e.equipment_type_id
                WHERE e.id=NEW.equipment_id AND t.measurement_unit IN ('km','hours')
                  AND ((t.measurement_unit='km' AND NEW.odometer IS NOT NULL AND NEW.hours IS NULL)
                    OR (t.measurement_unit='hours' AND NEW.hours IS NOT NULL AND NEW.odometer IS NULL))
            ) THEN RAISE(ABORT, 'وحدة قراءة العداد لا تطابق وحدة العتاد') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM meter_readings r
                WHERE r.equipment_id=NEW.equipment_id AND r.id<>NEW.id
                  AND date(r.reading_date)=date(NEW.reading_date)
            ) THEN RAISE(ABORT, 'توجد قراءة مسجلة لهذا العتاد في التاريخ نفسه') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM meter_readings r
                WHERE r.equipment_id=NEW.equipment_id AND r.id<>NEW.id
                  AND ((NEW.odometer IS NOT NULL AND r.odometer IS NOT NULL AND
                        ((date(r.reading_date)<date(NEW.reading_date) AND r.odometer>NEW.odometer)
                         OR (date(r.reading_date)>date(NEW.reading_date) AND r.odometer<NEW.odometer)))
                    OR (NEW.hours IS NOT NULL AND r.hours IS NOT NULL AND
                        ((date(r.reading_date)<date(NEW.reading_date) AND r.hours>NEW.hours)
                         OR (date(r.reading_date)>date(NEW.reading_date) AND r.hours<NEW.hours))))
            ) THEN RAISE(ABORT, 'تسلسل قراءة العداد يتعارض مع السجل المركزي') END;
        END
    """)
    for event in ("INSERT", "UPDATE"):
        old_equipment_refresh = """
            UPDATE equipment SET
                current_odometer=(SELECT r.odometer FROM meter_readings r
                    WHERE r.equipment_id=OLD.equipment_id AND r.odometer IS NOT NULL
                    ORDER BY r.reading_date DESC,r.id DESC LIMIT 1),
                current_hours=(SELECT r.hours FROM meter_readings r
                    WHERE r.equipment_id=OLD.equipment_id AND r.hours IS NOT NULL
                    ORDER BY r.reading_date DESC,r.id DESC LIMIT 1)
            WHERE id=OLD.equipment_id;
        """ if event == "UPDATE" else ""
        op.execute(f"""
            CREATE TRIGGER trg_meter_readings_refresh_{event.lower()}
            AFTER {event} ON meter_readings
            BEGIN
                {old_equipment_refresh}
                UPDATE equipment SET
                    current_odometer=(SELECT r.odometer FROM meter_readings r
                        WHERE r.equipment_id=NEW.equipment_id AND r.odometer IS NOT NULL
                        ORDER BY r.reading_date DESC,r.id DESC LIMIT 1),
                    current_hours=(SELECT r.hours FROM meter_readings r
                        WHERE r.equipment_id=NEW.equipment_id AND r.hours IS NOT NULL
                        ORDER BY r.reading_date DESC,r.id DESC LIMIT 1)
                WHERE id=NEW.equipment_id;
            END
        """)
    op.execute("""
        CREATE TRIGGER trg_meter_readings_refresh_delete
        AFTER DELETE ON meter_readings
        BEGIN
            UPDATE equipment SET
                current_odometer=(SELECT r.odometer FROM meter_readings r
                    WHERE r.equipment_id=OLD.equipment_id AND r.odometer IS NOT NULL
                    ORDER BY r.reading_date DESC,r.id DESC LIMIT 1),
                current_hours=(SELECT r.hours FROM meter_readings r
                    WHERE r.equipment_id=OLD.equipment_id AND r.hours IS NOT NULL
                    ORDER BY r.reading_date DESC,r.id DESC LIMIT 1)
            WHERE id=OLD.equipment_id;
        END
    """)


def _drop_sqlite_meter_triggers():
    if op.get_bind().dialect.name != "sqlite":
        return
    for name in (
        "trg_meter_readings_validate_insert", "trg_meter_readings_validate_update",
        "trg_meter_readings_refresh_insert", "trg_meter_readings_refresh_update",
        "trg_meter_readings_refresh_delete",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def upgrade():
    op.add_column("repairs", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()))
    op.add_column("maintenance_records", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()))
    for table, column, checks in (
        ("fuel_records", "meter_value", ()),
        ("faults", "meter_value", ("ck_fault_meter_nonnegative",)),
        ("repairs", "meter_value", ("ck_repair_meter_nonnegative",)),
        ("maintenance_records", "meter_value", ("ck_maintenance_record_meter_nonnegative",)),
        ("missions", "departure_meter", ("ck_mission_departure_meter",)),
        ("missions", "return_meter", ("ck_mission_return_meter",)),
        ("tire_movements", "meter_value", ()),
        ("battery_movements", "meter_value", ()),
    ):
        _drop_column(table, column, checks)
    # The ledger is now the only source of meter values. Rebuild the legacy
    # equipment cache from its latest central reading before installing guards.
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE equipment SET
            current_odometer=(SELECT r.odometer FROM meter_readings r
                WHERE r.equipment_id=equipment.id AND r.odometer IS NOT NULL
                ORDER BY r.reading_date DESC,r.id DESC LIMIT 1),
            current_hours=(SELECT r.hours FROM meter_readings r
                WHERE r.equipment_id=equipment.id AND r.hours IS NOT NULL
                ORDER BY r.reading_date DESC,r.id DESC LIMIT 1)
    """))
    _create_sqlite_meter_triggers()


def downgrade():
    _drop_sqlite_meter_triggers()
    # Restore compatibility columns and repopulate them from the central log.
    for table, column, nullable in (
        ("fuel_records", "meter_value", False),
        ("faults", "meter_value", True),
        ("repairs", "meter_value", True),
        ("maintenance_records", "meter_value", True),
        ("missions", "departure_meter", True),
        ("missions", "return_meter", True),
        ("tire_movements", "meter_value", True),
        ("battery_movements", "meter_value", True),
    ):
        op.add_column(table, sa.Column(column, sa.Numeric(10, 1), nullable=nullable, server_default="0" if not nullable else None))
    connection = op.get_bind()
    for table, column, reference in (
        ("fuel_records", "meter_value", "'fuel:' || id || ':meter'"),
        ("faults", "meter_value", "'fault:' || id || ':meter'"),
        ("repairs", "meter_value", "'repair:' || id || ':meter'"),
        ("tire_movements", "meter_value", "'tire_movement:' || id || ':meter'"),
        ("battery_movements", "meter_value", "'battery_movement:' || id || ':meter'"),
        ("missions", "departure_meter", "'mission:' || id || ':departure'"),
        ("missions", "return_meter", "'mission:' || id || ':return'"),
    ):
        connection.execute(sa.text(f"""
            UPDATE {table}
            SET {column} = (
                SELECT CASE WHEN odometer IS NOT NULL THEN odometer ELSE hours END
                FROM meter_readings WHERE source_reference = ({reference})
            )
        """))
    connection.execute(sa.text("""
        UPDATE maintenance_records
        SET meter_value = (
            SELECT CASE WHEN odometer IS NOT NULL THEN odometer ELSE hours END
            FROM meter_readings
            WHERE source_reference = CASE
                WHEN maintenance_records.plan_id IS NOT NULL THEN
                    'maintenance_plan:' || maintenance_records.plan_id || ':' || maintenance_records.equipment_id || ':' || maintenance_records.maintenance_date || ':meter'
                ELSE 'maintenance:' || maintenance_records.id || ':meter'
            END
        )
    """))
    op.drop_column("maintenance_records", "updated_at")
    op.drop_column("repairs", "updated_at")
