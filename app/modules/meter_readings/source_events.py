"""Keep all module supplied meter observations in the central meter ledger."""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import event, insert, or_, select, update

from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit import MeterReadingChange, utc_now


_registered = False


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return None


def _observations(connection, model_name, row):
    """Return (equipment, date, value, source, reference) tuples for one source row."""
    if model_name == "FuelRecord":
        return [(row.equipment_id, row.fueling_date, row.meter_value, "fuel", f"fuel:{row.id}:meter")]
    if model_name == "Fault":
        return [(row.equipment_id, row.reported_date, row.meter_value, "fault", f"fault:{row.id}:meter")]
    if model_name == "Repair":
        from app.modules.faults_repairs.models import Fault
        equipment_id = connection.execute(select(Fault.equipment_id).where(Fault.id == row.fault_id)).scalar_one_or_none()
        return [(equipment_id, row.repair_date, row.meter_value, "repair", f"repair:{row.id}:meter")]
    if model_name == "MaintenanceRecord":
        if row.plan_id is not None:
            # One plan execution can create one record per operation while
            # capturing a single physical meter reading. Keep that reading
            # singular in the ledger and identify it by the execution group.
            reference = f"maintenance_plan:{row.plan_id}:{row.equipment_id}:{row.maintenance_date}:meter"
        else:
            reference = f"maintenance:{row.id}:meter"
        value = None if row.is_scheduled else row.meter_value
        return [(row.equipment_id, row.maintenance_date, value, "maintenance", reference)]
    if model_name == "Mission":
        items = [(row.equipment_id, row.start_date, row.departure_meter, "mission_departure", f"mission:{row.id}:departure")]
        items.append((row.equipment_id, row.end_date, row.return_meter, "mission_return", f"mission:{row.id}:return"))
        return items
    if model_name == "TireMovement":
        return [(row.equipment_id, row.movement_date, row.meter_value, "tire_movement", f"tire_movement:{row.id}:meter")]
    if model_name == "BatteryMovement":
        return [(row.equipment_id, row.movement_date, row.meter_value, "battery_movement", f"battery_movement:{row.id}:meter")]
    return []


def _persist(connection, equipment_id, event_date, raw_value, source, reference):
    existing = connection.execute(
        select(MeterReading.id, MeterReading.equipment_id, MeterReading.reading_date, MeterReading.odometer, MeterReading.hours, MeterReading.source)
        .where(MeterReading.source_reference == reference)
    ).first()
    if raw_value is None or equipment_id is None or event_date is None:
        if existing is not None:
            reading_id, old_equipment_id, old_date, old_odometer, old_hours, old_source = existing
            unit = "km" if old_odometer is not None else "hours"
            old_value = old_odometer if unit == "km" else old_hours
            connection.execute(update(MeterReading).where(MeterReading.id == reading_id).values(source_reference=None))
            connection.execute(insert(MeterReadingChange.__table__).values(
                reading_id=reading_id, equipment_id=old_equipment_id, changed_at=utc_now(),
                action="unlink", source=old_source, reading_date=old_date, unit=unit,
                old_value=old_value, new_value=old_value,
                details="أزيلت القراءة من سجل العملية مع إبقائها في التاريخ المركزي.",
            ))
        return
    reading_date = _as_datetime(event_date)
    if reading_date is None:
        return
    if reading_date.date() > date.today():
        raise ValueError("لا يمكن إدخال قراءة بتاريخ مستقبلي")
    value = Decimal(str(raw_value))
    if value < 0:
        raise ValueError("قيمة العداد لا يمكن أن تكون سالبة")
    unit = connection.execute(
        select(EquipmentType.measurement_unit)
        .select_from(Equipment.__table__.join(EquipmentType.__table__, Equipment.equipment_type_id == EquipmentType.id))
        .where(Equipment.id == equipment_id)
    ).scalar_one_or_none()
    unit = (unit or "hours").strip().lower()
    if unit not in {"km", "hours"}:
        raise ValueError("وحدة قياس العداد غير معرفة بشكل صحيح")
    column = MeterReading.odometer if unit == "km" else MeterReading.hours
    value_column = "odometer" if unit == "km" else "hours"
    stmt = select(MeterReading.id, MeterReading.reading_date, column, MeterReading.source).where(
        MeterReading.equipment_id == equipment_id,
        or_(MeterReading.source_reference.is_(None), MeterReading.source_reference != reference),
        column.is_not(None),
    )
    for _, other_date, other_value, other_source in connection.execute(stmt):
        if other_date.date() == reading_date.date():
            if Decimal(str(other_value)) != value:
                raise ValueError(f"تعارض قراءة العداد بتاريخ {reading_date:%d/%m/%Y}: المصدر {source} لا يطابق {other_source}.")
            raise ValueError(f"قراءة العداد مكررة في {reading_date:%d/%m/%Y}.")
        if other_date.date() < reading_date.date() and Decimal(str(other_value)) > value:
            raise ValueError("قراءة العداد أقل من قراءة سابقة في السجل المركزي")
        if other_date.date() > reading_date.date() and Decimal(str(other_value)) < value:
            raise ValueError("قراءة العداد أكبر من قراءة لاحقة في السجل المركزي")
    if existing is not None:
        existing = (existing[0], existing[2], existing[3] if unit == "km" else existing[4], existing[5])
    values = {
        "equipment_id": equipment_id, "reading_date": reading_date,
        "odometer": value if unit == "km" else None,
        "hours": value if unit == "hours" else None,
        "source": source, "source_reference": reference,
        "equipment_status": "available",
    }
    if existing is None:
        connection.execute(insert(MeterReading).values(**values))
        reading_id = connection.execute(
            select(MeterReading.id).where(MeterReading.source_reference == reference)
        ).scalar_one()
        action, old_value = "add", None
    else:
        reading_id, old_date, old_value, old_source = existing
        connection.execute(update(MeterReading).where(MeterReading.id == reading_id).values(**values))
        action = "update"
    if existing is None or old_value != value or existing[1] != reading_date or existing[3] != source:
        connection.execute(insert(MeterReadingChange.__table__).values(
            reading_id=reading_id, equipment_id=equipment_id, changed_at=utc_now(),
            action=action, source=source, reading_date=reading_date, unit=unit,
            old_value=old_value, new_value=value,
            details="تسجيل قراءة من عملية " + source + " في السجل المركزي.",
        ))
    latest = connection.execute(
        select(column).where(MeterReading.equipment_id == equipment_id, column.is_not(None))
        .order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).limit(1)
    ).scalar_one_or_none()
    current_field = Equipment.current_odometer if unit == "km" else Equipment.current_hours
    connection.execute(update(Equipment).where(Equipment.id == equipment_id).values({current_field.key: latest}))


def register_domain_meter_listeners():
    global _registered
    if _registered:
        return
    from app.modules.faults_repairs.models import Fault, Repair
    from app.modules.fuel.models import FuelRecord
    from app.modules.maintenance.models import MaintenanceRecord
    from app.modules.missions.models import Mission
    from app.modules.tires.models import TireMovement
    from app.modules.batteries.models import BatteryMovement

    sources = (FuelRecord, Fault, Repair, MaintenanceRecord, Mission, TireMovement, BatteryMovement)
    for model in sources:
        for operation in ("after_insert", "after_update"):
            def listener(mapper, connection, target, _model=model):
                for equipment_id, event_date, value, source, reference in _observations(connection, _model.__name__, target):
                    _persist(connection, equipment_id, event_date, value, source, reference)
            event.listen(model, operation, listener)
    _registered = True
