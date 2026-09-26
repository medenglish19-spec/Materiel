from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Text, Boolean, DateTime, UniqueConstraint, CheckConstraint, Index, event, select, desc
from sqlalchemy.orm import relationship
from sqlalchemy import inspect

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class MaintenanceOperationGroup(Base):
    __tablename__ = "maintenance_operation_groups"
    __table_args__ = (
        UniqueConstraint("name", name="uq_maintenance_operation_group_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    operations = relationship("MaintenanceOperation", back_populates="group")


class MaintenanceOperation(Base):
    __tablename__ = "maintenance_operations"
    __table_args__ = (
        CheckConstraint("interval_km IS NOT NULL OR interval_hours IS NOT NULL OR interval_days IS NOT NULL", name="ck_maintenance_operation_has_interval"),
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_operation_interval_km_positive"),
        CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_operation_interval_hours_positive"),
        CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_operation_interval_days_positive"),
        CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_operation_warning_km_nonnegative"),
        CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_operation_warning_days_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    warning_km = Column(Numeric(10, 1), nullable=True)
    warning_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    description = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("maintenance_operation_groups.id", name="fk_maintenance_operations_group", ondelete="SET NULL"), nullable=True, index=True)

    group = relationship("MaintenanceOperationGroup", back_populates="operations")
    plan_operations = relationship("MaintenancePlanOperation", back_populates="operation")
    records = relationship("MaintenanceRecord", back_populates="operation")


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"
    __table_args__ = (
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_plan_interval_km_positive"),
        CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_plan_interval_hours_positive"),
        CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_plan_interval_days_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_model_id = Column(
        Integer,
        ForeignKey("equipment_models.id", name="fk_maintenance_plans_equipment_model", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    description = Column(Text, nullable=True)

    equipment_model = relationship("EquipmentModel")
    plan_operations = relationship(
        "MaintenancePlanOperation",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    records = relationship("MaintenanceRecord", back_populates="plan")


class MaintenancePlanOperation(Base):
    __tablename__ = "maintenance_plan_operations"
    __table_args__ = (
        UniqueConstraint("plan_id", "operation_id", name="uq_maintenance_plan_operation"),
    )

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(
        Integer,
        ForeignKey("maintenance_plans.id", name="fk_maintenance_plan_operations_plan", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id = Column(
        Integer,
        ForeignKey("maintenance_operations.id", name="fk_maintenance_plan_operations_operation", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    plan = relationship("MaintenancePlan", back_populates="plan_operations")
    operation = relationship("MaintenanceOperation", back_populates="plan_operations")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        Index("uq_maintenance_record_equipment_operation_date", "equipment_id", "operation_id", "maintenance_date", unique=True),
        CheckConstraint("meter_value IS NULL OR meter_value >= 0", name="ck_maintenance_record_meter_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_id = Column(
        Integer,
        ForeignKey("maintenance_operations.id", name="fk_maintenance_records_operation", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    plan_id = Column(
        Integer,
        ForeignKey("maintenance_plans.id", name="fk_maintenance_records_plan", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    operation = relationship("MaintenanceOperation", back_populates="records", foreign_keys=[operation_id])
    plan = relationship("MaintenancePlan", back_populates="records")
    created_by = relationship("User", foreign_keys=[created_by_id])


def _validate_record(connection, target, exclude_id=None):
    if target.equipment_id is None:
        raise ValueError("يجب تحديد العتاد قبل تسجيل الصيانة.")
    if getattr(target, "operation_id", None) is None:
        raise ValueError("يجب تحديد عملية الصيانة قبل تسجيل السجل.")
    operation_id = getattr(target, "operation_id", None)
    plan_id = getattr(target, "plan_id", None)
    if plan_id is not None and operation_id is None:
        raise ValueError("خطة الصيانة لا يمكن ربطها بسجل تنفيذ دون تحديد عملية الصيانة.")
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

    equipment_row = connection.execute(
        select(Equipment.equipment_model_id)
        .where(Equipment.id == target.equipment_id)
    ).first()
    if equipment_row is None:
        raise ValueError("العتاد المحدد غير موجود.")
    equipment_model_id = equipment_row[0]
    if equipment_model_id is None:
        raise ValueError("يجب تحديد طراز العتاد قبل تسجيل الصيانة.")

    if operation_id is not None:
        operation_row = connection.execute(
            select(MaintenanceOperation.id, MaintenanceOperation.is_active, MaintenanceOperation.old_rule_id)
            .where(MaintenanceOperation.id == operation_id)
        ).first()
        if operation_row is None:
            raise ValueError("عملية الصيانة المحددة غير موجودة.")
        if not operation_row[1]:
            raise ValueError("عملية الصيانة غير مفعلة.")

        if target.rule_id is not None and operation_row[2] != target.rule_id:
            mapping = connection.execute(
                select(MaintenanceOperationRuleMap.id)
                .where(
                    MaintenanceOperationRuleMap.old_rule_id == target.rule_id,
                    MaintenanceOperationRuleMap.operation_id == operation_id,
                )
            ).first()
            if mapping is None:
                raise ValueError("الصيانة الدورية القديمة لا تقابل عملية الصيانة المختارة.")

        membership = connection.execute(
            select(MaintenancePlanOperation.id)
            .join(MaintenancePlan, MaintenancePlan.id == MaintenancePlanOperation.plan_id)
            .where(
                MaintenancePlanOperation.operation_id == operation_id,
                MaintenancePlan.equipment_model_id == equipment_model_id,
                MaintenancePlan.is_active.is_(True),
            )
        ).first()
        has_any_membership = connection.execute(
            select(MaintenancePlanOperation.id)
            .where(MaintenancePlanOperation.operation_id == operation_id)
        ).first() is not None

        if membership is None and has_any_membership and plan_id is None:
            raise ValueError("عملية الصيانة لا تنتمي إلى خطة مفعلة لهذا الطراز.")
        if membership is None and not has_any_membership and plan_id is not None:
            raise ValueError("لا يمكن ربط عملية مستقلة بخطة دون إدراجها فيها.")

        if plan_id is not None:
            plan_row = connection.execute(
                select(MaintenancePlan.equipment_model_id, MaintenancePlan.is_active)
                .where(MaintenancePlan.id == plan_id)
            ).first()
            if plan_row is None:
                raise ValueError("خطة الصيانة المحددة غير موجودة.")
            if not plan_row[1]:
                raise ValueError("خطة الصيانة غير مفعلة.")
            if plan_row[0] != equipment_model_id:
                raise ValueError("خطة الصيانة لا تخص طراز العتاد المحدد.")
            linked = connection.execute(
                select(MaintenancePlanOperation.id)
                .where(
                    MaintenancePlanOperation.plan_id == plan_id,
                    MaintenancePlanOperation.operation_id == operation_id,
                )
            ).first()
            if linked is None:
                raise ValueError("عملية الصيانة غير مرتبطة بالخطة المحددة.")

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
        if previous_date == target.maintenance_date:
            if exclude_id is None:
                # A new record is appended after existing same-day records.
                if target.meter_value < previous_meter:
                    raise ValueError(f"⚠ تناقض في نفس يوم الصيانة: القراءة ({target.meter_value:g}) أقل من قراءة سجل سابق في اليوم نفسه ({previous_meter:g}).")
            elif previous_id < target.id and target.meter_value < previous_meter:
                raise ValueError(f"⚠ تناقض في نفس يوم الصيانة: القراءة ({target.meter_value:g}) أقل من سجل سابق ({previous_meter:g}).")
            elif previous_id > target.id and target.meter_value > previous_meter:
                raise ValueError(f"⚠ تناقض في نفس يوم الصيانة: القراءة ({target.meter_value:g}) أكبر من سجل لاحق ({previous_meter:g}).")

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
