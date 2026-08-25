from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, String, event, func, select, insert, or_, and_
from sqlalchemy.orm import relationship
from sqlalchemy import inspect

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.meter_readings.audit import MeterReadingChange, utc_now


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    reading_date = Column(DateTime, nullable=False, default=utc_now)
    created_at = Column(DateTime, nullable=False, default=utc_now, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, default=utc_now, server_default=func.current_timestamp(), onupdate=utc_now)
    odometer = Column(Numeric(10, 1), nullable=True)
    hours = Column(Numeric(10, 1), nullable=True)
    source = Column(String(50), nullable=False, default="manual")
    equipment_status = Column(String(30), nullable=False, default="available", server_default="available")
    notes = Column(String(300), nullable=True)
    equipment = relationship("Equipment")


def _equipment_unit(connection, equipment_id):
    row = connection.execute(
        select(Equipment.equipment_type_id).where(Equipment.id == equipment_id)
    ).first()
    if row is None:
        raise ValueError("المعدة المحددة غير موجودة.")
    from app.modules.equipment_types.models import EquipmentType
    unit = connection.execute(
        select(EquipmentType.measurement_unit).where(EquipmentType.id == row[0])
    ).scalar_one_or_none()
    return (unit or "").strip().lower()


def _validate_meter_payload(connection, target, exclude_id=None):
    if target.equipment_id is None:
        raise ValueError("يجب تحديد المعدة قبل تسجيل قراءة العداد.")
    unit = _equipment_unit(connection, target.equipment_id)
    if unit not in ("km", "hours"):
        raise ValueError("وحدة قياس المعدة غير معرفة بشكل صحيح (km أو hours).")

    if unit == "km":
        if target.odometer is None or target.hours is not None:
            raise ValueError("هذه المعدة تعمل بالكيلومترات؛ يجب إدخال odometer فقط.")
        value_column = MeterReading.odometer
        value = target.odometer
    else:
        if target.hours is None or target.odometer is not None:
            raise ValueError("هذه المعدة تعمل بالساعات؛ يجب إدخال hours فقط.")
        value_column = MeterReading.hours
        value = target.hours

    if value < 0:
        raise ValueError("لا يمكن أن تكون قراءة العداد سالبة.")

    query = select(value_column, MeterReading.reading_date).where(MeterReading.equipment_id == target.equipment_id)
    if exclude_id is not None:
        query = query.where(MeterReading.id != exclude_id)
    rows = connection.execute(query).all()

    # The meter must never move backwards relative to any older reading.
    for existing_value, existing_date in rows:
        if existing_value is None or existing_date is None:
            continue
        if target.reading_date.date() > existing_date.date() and value < existing_value:
            raise ValueError(
                f"قراءة العداد الجديدة ({value:g}) أقل من قراءة سابقة ({existing_value:g})؛ لا يمكن أن يعود العداد إلى الخلف."
            )
        if target.reading_date.date() == existing_date.date() and value != existing_value:
            raise ValueError(
                "لا يمكن تسجيل قراءتين مختلفتين لنفس المعدة في نفس التاريخ."
            )


@event.listens_for(MeterReading, "before_insert")
def _validate_meter_reading(mapper, connection, target):
    now = datetime.now(timezone.utc)
    if target.created_at is None:
        target.created_at = now
    if target.updated_at is None:
        target.updated_at = now
    if target.reading_date is not None and target.reading_date.date() > now.date():
        raise ValueError("لا يمكن إدخال قراءة بتاريخ مستقبلي.")
    _validate_meter_payload(connection, target)
    if not target.equipment_status:
        status = connection.execute(
            select(Equipment.operational_status).where(Equipment.id == target.equipment_id)
        ).scalar_one_or_none()
        target.equipment_status = status or "available"


@event.listens_for(MeterReading, "before_update")
def _prevent_invalid_meter_update(mapper, connection, target):
    state = inspect(target)
    if not any(state.attrs[name].history.has_changes() for name in ("equipment_id", "reading_date", "odometer", "hours")):
        return
    if target.reading_date is None or target.equipment_id is None:
        return
    now = datetime.now(timezone.utc)
    if target.reading_date.date() > now.date():
        raise ValueError("لا يمكن تعديل قراءة إلى تاريخ مستقبلي.")
    _validate_meter_payload(connection, target, exclude_id=target.id)


@event.listens_for(MeterReading, "after_insert")
def _audit_meter_insert(mapper, connection, target):
    unit = "km" if target.odometer is not None else "hours"
    value = target.odometer if unit == "km" else target.hours
    connection.execute(insert(MeterReadingChange.__table__).values(
        reading_id=target.id,
        equipment_id=target.equipment_id,
        changed_at=utc_now(),
        action="add",
        source=target.source or "manual",
        reading_date=target.reading_date,
        unit=unit,
        old_value=None,
        new_value=value,
        details="إضافة قراءة جديدة إلى النظام.",
    ))


@event.listens_for(MeterReading, "after_update")
def _audit_meter_update(mapper, connection, target):
    state = inspect(target)
    unit = "km" if target.odometer is not None else "hours"
    attr = "odometer" if unit == "km" else "hours"
    history = state.attrs[attr].history
    if not history.has_changes():
        return
    old_value = history.deleted[0] if history.deleted else None
    new_value = history.added[0] if history.added else None
    connection.execute(insert(MeterReadingChange.__table__).values(
        reading_id=target.id,
        equipment_id=target.equipment_id,
        changed_at=utc_now(),
        action="update",
        source=target.source or "manual",
        reading_date=target.reading_date,
        unit=unit,
        old_value=old_value,
        new_value=new_value,
        details="تعديل قيمة قراءة مسجلة.",
    ))
