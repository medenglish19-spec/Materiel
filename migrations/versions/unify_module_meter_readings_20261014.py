"""Unify module meter observations in the central reading ledger.

Revision ID: unify_module_meter_readings_20261014
Revises: remove_closed_fault_status_20261013
"""
from alembic import op
import sqlalchemy as sa


revision = "unify_module_meter_readings_20261014"
down_revision = "remove_closed_fault_status_20261013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("meter_readings", sa.Column("source_reference", sa.String(length=120), nullable=True))
    op.create_index("ix_meter_readings_source_reference", "meter_readings", ["source_reference"], unique=True)
    connection = op.get_bind()
    # Import existing domain observations once so their values and provenance
    # remain available in the central history after the new write path is used.
    sources = [
        ("fuel_records", "equipment_id", "fueling_date", "meter_value", "fuel", "id", "meter"),
        ("faults", "equipment_id", "reported_date", "meter_value", "fault", "id", "meter"),
        ("maintenance_records", "equipment_id", "maintenance_date", "meter_value", "maintenance", "id", "meter"),
    ]
    for table, equipment_col, date_col, value_col, source, id_col, field in sources:
        source_filter = " AND src.is_scheduled = 0" if source == "maintenance" else ""
        reference_expression = (
            "CASE WHEN src.plan_id IS NOT NULL THEN 'maintenance_plan' || char(58) || src.plan_id || char(58) || src.equipment_id || char(58) || src.maintenance_date || char(58) || 'meter' "
            "ELSE 'maintenance' || char(58) || src.id || char(58) || 'meter' END"
            if source == "maintenance"
            else f":source || char(58) || src.{id_col} || char(58) || :field"
        )
        connection.execute(sa.text(f"""
            INSERT OR IGNORE INTO meter_readings
                (equipment_id, reading_date, odometer, hours, source, source_reference, equipment_status, created_at, updated_at)
            SELECT src.{equipment_col}, datetime(src.{date_col}),
                   CASE WHEN et.measurement_unit = 'km' THEN src.{value_col} END,
                   CASE WHEN et.measurement_unit = 'hours' THEN src.{value_col} END,
                   :source, {reference_expression}, 'available', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM {table} AS src
            JOIN equipment AS e ON e.id = src.{equipment_col}
            JOIN equipment_types AS et ON et.id = e.equipment_type_id
            WHERE src.{value_col} IS NOT NULL
              {source_filter}
        """), {"source": source, "field": field})
    connection.execute(sa.text("""
        INSERT OR IGNORE INTO meter_readings
            (equipment_id, reading_date, odometer, hours, source, source_reference, equipment_status, created_at, updated_at)
        SELECT f.equipment_id, datetime(r.repair_date),
               CASE WHEN et.measurement_unit = 'km' THEN r.meter_value END,
               CASE WHEN et.measurement_unit = 'hours' THEN r.meter_value END,
               'repair', 'repair' || char(58) || r.id || char(58) || 'meter', 'available', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM repairs r JOIN faults f ON f.id = r.fault_id
        JOIN equipment e ON e.id = f.equipment_id
        JOIN equipment_types et ON et.id = e.equipment_type_id
        WHERE r.meter_value IS NOT NULL
    """))
    connection.execute(sa.text("""
        INSERT OR IGNORE INTO meter_readings
            (equipment_id, reading_date, odometer, hours, source, source_reference, equipment_status, created_at, updated_at)
        SELECT m.equipment_id, datetime(m.start_date),
               CASE WHEN et.measurement_unit = 'km' THEN m.departure_meter END,
               CASE WHEN et.measurement_unit = 'hours' THEN m.departure_meter END,
               'mission_departure', 'mission' || char(58) || m.id || char(58) || 'departure', 'available', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM missions m JOIN equipment e ON e.id = m.equipment_id
        JOIN equipment_types et ON et.id = e.equipment_type_id
        WHERE m.departure_meter IS NOT NULL
    """))
    connection.execute(sa.text("""
        INSERT OR IGNORE INTO meter_readings
            (equipment_id, reading_date, odometer, hours, source, source_reference, equipment_status, created_at, updated_at)
        SELECT m.equipment_id, datetime(m.end_date),
               CASE WHEN et.measurement_unit = 'km' THEN m.return_meter END,
               CASE WHEN et.measurement_unit = 'hours' THEN m.return_meter END,
               'mission_return', 'mission' || char(58) || m.id || char(58) || 'return', 'available', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM missions m JOIN equipment e ON e.id = m.equipment_id
        JOIN equipment_types et ON et.id = e.equipment_type_id
        WHERE m.end_date IS NOT NULL AND m.return_meter IS NOT NULL
    """))
    for table, date_col in (("tire_movements", "movement_date"), ("battery_movements", "movement_date")):
        source = "tire_movement" if table == "tire_movements" else "battery_movement"
        connection.execute(sa.text(f"""
            INSERT OR IGNORE INTO meter_readings
                (equipment_id, reading_date, odometer, hours, source, source_reference, equipment_status, created_at, updated_at)
            SELECT src.equipment_id, datetime(src.{date_col}),
                   CASE WHEN et.measurement_unit = 'km' THEN src.meter_value END,
                   CASE WHEN et.measurement_unit = 'hours' THEN src.meter_value END,
                   :source, :source || char(58) || src.id || char(58) || 'meter', 'available', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM {table} src JOIN equipment e ON e.id = src.equipment_id
            JOIN equipment_types et ON et.id = e.equipment_type_id
            WHERE src.equipment_id IS NOT NULL AND src.meter_value IS NOT NULL
        """), {"source": source})


def downgrade():
    op.drop_index("ix_meter_readings_source_reference", table_name="meter_readings")
    op.drop_column("meter_readings", "source_reference")
