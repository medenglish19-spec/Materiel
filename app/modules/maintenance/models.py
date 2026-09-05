from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Text, Boolean, DateTime, UniqueConstraint, CheckConstraint, event, select, desc
from sqlalchemy.orm import relationship
from sqlalchemy import inspect

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class MaintenanceRule(Base):
    __tablename__ = "maintenance_rules"
    __table_args__ = (
        CheckConstraint("interval_km IS NOT NULL OR interval_hours IS NOT NULL OR interval_days IS NOT NULL", name="ck_maintenance_rule_has_interval"),
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_rule_interval_km_positive"),
        CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_rule_interval_hours_positive"),
        CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_rule_interval_days_positive"),
        CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_rule_warning_km_nonnegative"),
        CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_rule_warning_days_nonnegative"),
        CheckConstraint("equipment_model_id IS NOT NULL OR is_active = 0", name="ck_maintenance_rule_active_requires_model"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    equipment_type_id = Column(Integer, ForeignKey("equipment_types.id", ondelete="CASCADE"), nullable=False, index=True)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_rule_id = Column(Integer, ForeignKey("maintenance_rules.id", ondelete="CASCADE"), nullable=True, index=True)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    warning_km = Column(Numeric(10, 1), nullable=True, default=500)
    warning_days = Column(Integer, nullable=True, default=7)
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)

    equipment_type = relationship("EquipmentType")
    equipment_model = relationship("EquipmentModel", foreign_keys=[equipment_model_id])
    parent_rule = relationship("MaintenanceRule", remote_side=[id], foreign_keys=[parent_rule_id])
    records = relationship("MaintenanceRecord", back_populates="rule")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        UniqueConstraint("equipment_id", "rule_id", "maintenance_date", name="uq_maintenance_record_equipment_rule_date"),
        CheckConstraint("meter_value IS NULL OR meter_value >= 0", name="ck_maintenance_record_meter_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("maintenance_rules.id", ondelete="RESTRICT"), nullable=False, index=True)
    maintenance_date = Column(Date, nullable=False)
    reported_date = Column(Date, nullable=False)
    meter_value = Column(Numeric(10, 1), nullable=True)
    work_order = Column(String(80), nullable=True)
    workshop = Column(String(120), nullable=True)
    status = Column(String(30), nullable=False, default="completed")
    is_scheduled = Column(Boolean, nullable=False, default=False, server_default="0")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    equipment = relationship("Equipment", back_populates="maintenance_records")
    rule = relationship("MaintenanceRule", back_populates="records")
    created_by = relationship("User", foreign_keys=[created_by_id])


def _validate_record(connection, target, exclude_id=None):
    if target.equipment_id is None:
        raise ValueError("يجب تحديد العتاد قبل تسجيل الصيانة.")
    if target.rule_id is None:
        raise ValueError("يجب تحديد الصيانة الدورية قبل تسجيل السجل.")
    if target.maintenance_date is None:
        raise ValueError("يجب تحديد تاريخ الصيانة.")
    if target.maintenance_date > datetime.now(timezone.utc).date():
        raise ValueError("لا يمكن تسجيل صيانة بتاريخ مستقبلي.")
    if target.meter_value is not None and target.meter_value < 0:
        raise ValueError("لا يمكن أن تكون قراءة العداد عند الصيانة سالبة.")

    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType
    from app.modules.meter_readings.models import MeterReading

    unit = connection.execute(
        select(EquipmentType.measurement_unit)
        .join(Equipment, Equipment.equipment_type_id == EquipmentType.id)
        .where(Equipment.id == target.equipment_id)
    ).scalar_one_or_none()
    unit = (unit or "").strip().lower()
    if unit not in ("km", "hours"):
        raise ValueError("وحدة قياس العتاد غير معرفة بشكل صحيح (km أو hours).")

    rule_row = connection.execute(
        select(MaintenanceRule.equipment_model_id)
        .where(MaintenanceRule.id == target.rule_id)
    ).first()
    equipment_row = connection.execute(
        select(Equipment.equipment_model_id)
        .where(Equipment.id == target.equipment_id)
    ).first()
    if rule_row is None or equipment_row is None:
        raise ValueError("الصيانة الدورية أو العتاد المحدد غير موجود.")
    if rule_row.equipment_model_id is None:
        raise ValueError("لا يمكن تسجيل صيانة بقاعدة قديمة غير مرتبطة بطراز.")
    if equipment_row.equipment_model_id is None:
        raise ValueError("يجب تحديد طراز العتاد قبل تسجيل الصيانة.")
    if rule_row.equipment_model_id != equipment_row.equipment_model_id:
        raise ValueError("الصيانة الدورية المختارة مخصصة لطراز آخر من العتاد.")

    if target.meter_value is None:
        return

    maintenance_query = select(
        MaintenanceRecord.maintenance_date,
        MaintenanceRecord.meter_value,
        MaintenanceRecord.id,
    ).where(
        MaintenanceRecord.equipment_id == target.equipment_id,
        MaintenanceRecord.meter_value.is_not(None),
    ).order_by(MaintenanceRecord.maintenance_date, MaintenanceRecord.id)
    for previous_date, previous_meter, previous_id in connection.execute(maintenance_query).all():
        if exclude_id is not None and previous_id == exclude_id:
            continue
        if previous_date < target.maintenance_date and target.meter_value < previous_meter:
            raise ValueError(f"⚠ تناقض بين التاريخ وقراءة العداد: القراءة ({target.meter_value:g}) أقل من قراءة أحدث زمنيًا قبلها ({previous_meter:g}).")
        if previous_date > target.maintenance_date and target.meter_value > previous_meter:
            raise ValueError(f"⚠ تناقض بين التاريخ وقراءة العداد: القراءة ({target.meter_value:g}) أكبر من قراءة سجل أحدث ({previous_meter:g}).")

    reading_column = MeterReading.odometer if unit == "km" else MeterReading.hours
    reading_query = select(MeterReading.reading_date, reading_column).where(
        MeterReading.equipment_id == target.equipment_id,
        reading_column.is_not(None),
    ).order_by(MeterReading.reading_date, MeterReading.id)
    for reading_date, reading_meter in connection.execute(reading_query).all():
        reading_day = reading_date.date() if hasattr(reading_date, "date") else reading_date
        reading_meter = Decimal(str(reading_meter))
        if reading_day < target.maintenance_date and target.meter_value < reading_meter:
            raise ValueError(f"⚠ تناقض بين الصيانة وقراءة العداد: قراءة الصيانة ({target.meter_value:g}) أقل من قراءة عداد أقدم ({reading_meter:g}).")
        if reading_day > target.maintenance_date and target.meter_value > reading_meter:
            raise ValueError(f"⚠ تناقض بين الصيانة وقراءة العداد: قراءة الصيانة ({target.meter_value:g}) أكبر من قراءة عداد أحدث ({reading_meter:g}).")


def _sync_equipment_current(connection, equipment_id):
    """Keep Equipment.current_* synchronized with the latest trusted meter observation."""
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType
    from app.modules.meter_readings.models import MeterReading

    unit = connection.execute(
        select(EquipmentType.measurement_unit)
        .join(Equipment, Equipment.equipment_type_id == EquipmentType.id)
        .where(Equipment.id == equipment_id)
    ).scalar_one_or_none()
    unit = (unit or "").strip().lower()
    if unit not in ("km", "hours"):
        return

    reading_column = MeterReading.odometer if unit == "km" else MeterReading.hours
    latest_reading = connection.execute(
        select(MeterReading.reading_date, reading_column)
        .where(MeterReading.equipment_id == equipment_id, reading_column.is_not(None))
        .order_by(desc(MeterReading.reading_date), desc(MeterReading.id))
        .limit(1)
    ).first()
    latest_maintenance = connection.execute(
        select(MaintenanceRecord.maintenance_date, MaintenanceRecord.meter_value)
        .where(MaintenanceRecord.equipment_id == equipment_id, MaintenanceRecord.meter_value.is_not(None))
        .order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id))
        .limit(1)
    ).first()

    candidates = []
    if latest_reading is not None:
        reading_date = latest_reading[0].date() if hasattr(latest_reading[0], "date") else latest_reading[0]
        candidates.append((reading_date, Decimal(str(latest_reading[1]))))
    if latest_maintenance is not None:
        candidates.append((latest_maintenance[0], Decimal(str(latest_maintenance[1]))))
    if not candidates:
        return

    latest_date = max(item[0] for item in candidates)
    current_value = max(value for item_date, value in candidates if item_date == latest_date)
    values = {"current_odometer": current_value} if unit == "km" else {"current_hours": current_value}
    connection.execute(
        Equipment.__table__.update().where(Equipment.id == equipment_id).values(**values)
    )


@event.listens_for(MaintenanceRecord, "before_insert")
def _validate_maintenance_record_insert(mapper, connection, target):
    target.reported_date = target.maintenance_date
    _validate_record(connection, target)


@event.listens_for(MaintenanceRecord, "after_insert")
def _sync_maintenance_record_insert(mapper, connection, target):
    _sync_equipment_current(connection, target.equipment_id)


@event.listens_for(MaintenanceRecord, "before_update")
def _validate_maintenance_record_update(mapper, connection, target):
    target.reported_date = target.maintenance_date
    state = inspect(target)
    if any(state.attrs[name].history.has_changes() for name in ("equipment_id", "rule_id", "maintenance_date", "meter_value")):
        _validate_record(connection, target, exclude_id=target.id)


@event.listens_for(MaintenanceRecord, "after_update")
def _sync_maintenance_record_update(mapper, connection, target):
    state = inspect(target)
    equipment_ids = {target.equipment_id}
    equipment_ids.update(state.attrs.equipment_id.history.deleted)
    for equipment_id in equipment_ids:
        if equipment_id is not None:
            _sync_equipment_current(connection, equipment_id)


@event.listens_for(MaintenanceRecord, "after_delete")
def _sync_maintenance_record_delete(mapper, connection, target):
    _sync_equipment_current(connection, target.equipment_id)
