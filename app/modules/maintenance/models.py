from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Text, Boolean, DateTime, LargeBinary, UniqueConstraint, CheckConstraint, Index, Table, event, select
from sqlalchemy.orm import relationship
from sqlalchemy import inspect

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


# Relation MaintenanceOperation <-> EquipmentModel.
#
# This relation — not the operation row — carries the technical eligibility
# condition and the warning settings of one model. The same operation can be
# linked to several models with different conditions, and editing one model's
# condition never touches another model's row.
#
# `condition_source` distinguishes two states that would otherwise both look
# like NULL columns:
#   * "unset"  → no condition has been configured for this model yet.
#                Nothing may be inferred from the operation or from another
#                model in this case; the UI reports «الشرط غير محدد».
#   * "model"  → the model's condition is configured (columns may still be
#                empty on purpose, e.g. the model has no active warning).
maintenance_operation_models = Table(
    "maintenance_operation_models",
    Base.metadata,
    Column("operation_id", Integer, ForeignKey("maintenance_operations.id", name="fk_maintenance_operation_models_operation", ondelete="CASCADE"), primary_key=True),
    Column("equipment_model_id", Integer, ForeignKey("equipment_models.id", name="fk_maintenance_operation_models_equipment_model", ondelete="CASCADE"), primary_key=True),
    Column("condition_source", String(20), nullable=False, default="unset", server_default="unset"),
    Column("interval_km", Numeric(10, 1), nullable=True),
    Column("interval_hours", Numeric(10, 1), nullable=True),
    Column("interval_days", Integer, nullable=True),
    Column("is_active", Boolean, nullable=False, default=True, server_default="1"),
    UniqueConstraint("operation_id", "equipment_model_id", name="pk_maintenance_operation_models"),
    Index("ix_maintenance_operation_models_equipment_model_id", "equipment_model_id"),
)

# Deliberately no CheckConstraint forcing a non-null interval here: a model row
# may exist with its condition still unset, and the application must report
# that state instead of inventing a value. Positive-value validation lives in
# `app/modules/maintenance/schemas.py`.


class MaintenanceOperationGroup(Base):
    __tablename__ = "maintenance_operation_groups"
    __table_args__ = (
        UniqueConstraint("name", name="uq_maintenance_operation_group_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    operations = relationship("MaintenanceOperation", back_populates="group")
    model_operations = relationship("MaintenanceModelOperation", back_populates="group")


class MaintenanceCatalogImport(Base):
    """Versioned, reviewable manufacturer source; never an operational plan."""
    __tablename__ = "maintenance_catalog_imports"
    __table_args__ = (
        UniqueConstraint("equipment_model_id", "content_sha256", name="uq_maintenance_catalog_model_sha256"),
        CheckConstraint("status IN ('draft', 'reviewed', 'applied', 'rejected')", name="ck_maintenance_catalog_import_status"),
    )

    id = Column(Integer, primary_key=True)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", name="fk_maintenance_catalog_imports_equipment_model", ondelete="RESTRICT"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    manufacturer = Column(String(160), nullable=True)
    document_title = Column(String(255), nullable=True)
    document_version = Column(String(120), nullable=True)
    filename = Column(String(255), nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    file_type = Column(String(16), nullable=False)
    source_file = Column(LargeBinary, nullable=False)
    extracted_text = Column(Text, nullable=False, default="")
    items_json = Column(Text, nullable=False, default="[]")
    warnings_json = Column(Text, nullable=False, default="[]")
    status = Column(String(20), nullable=False, default="draft", server_default="draft", index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", name="fk_maintenance_catalog_imports_created_by", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", name="fk_maintenance_catalog_imports_reviewed_by", ondelete="SET NULL"), nullable=True, index=True)

    equipment_model = relationship("EquipmentModel")
    created_by = relationship("User", foreign_keys=[created_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class MaintenanceOperation(Base):
    __tablename__ = "maintenance_operations"
    # لا قيد يفرض فاصلًا على مستوى العملية: شرط الاستحقاق يخص علاقة الطراز،
    # والعملية العامة في المكتبة قد تكون بلا أي شرط. الأعمدة القديمة تبقى في
    # المخطط بلا استخدام في الحساب، وتبقى قيود القيم الموجبة عليها.
    __table_args__ = (
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_operation_interval_km_positive"),
        CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_operation_interval_hours_positive"),
        CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_operation_interval_days_positive"),
        CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_operation_warning_km_nonnegative"),
        CheckConstraint("warning_hours IS NULL OR warning_hours >= 0", name="ck_maintenance_operation_warning_hours_nonnegative"),
        CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_operation_warning_days_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    warning_km = Column(Numeric(10, 1), nullable=True)
    warning_hours = Column(Numeric(10, 1), nullable=True)
    warning_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    description = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("maintenance_operation_groups.id", name="fk_maintenance_operations_group", ondelete="SET NULL"), nullable=True, index=True)

    group = relationship("MaintenanceOperationGroup", back_populates="operations")
    plan_operations = relationship("MaintenancePlanOperation", back_populates="operation")
    records = relationship("MaintenanceRecord", back_populates="operation")
    equipment_models = relationship(
        "EquipmentModel",
        secondary="maintenance_operation_models",
        back_populates="maintenance_operations",
    )

    @property
    def equipment_model_ids(self) -> list[int]:
        """Return list of equipment model IDs this operation applies to."""
        return [m.id for m in self.equipment_models]


class MaintenanceModelOperation(Base):
    """An operation imported into exactly one equipment model's private library."""
    __tablename__ = "maintenance_model_operations"
    __table_args__ = (
        CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_model_operation_interval_km_positive"),
        CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_model_operation_interval_hours_positive"),
        CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_model_operation_interval_days_positive"),
        CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_model_operation_warning_km_nonnegative"),
        CheckConstraint("warning_hours IS NULL OR warning_hours >= 0", name="ck_maintenance_model_operation_warning_hours_nonnegative"),
        CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_model_operation_warning_days_nonnegative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_model_id = Column(
        Integer,
        ForeignKey("equipment_models.id", name="fk_maintenance_model_operations_equipment_model", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("maintenance_operation_groups.id", name="fk_maintenance_model_operations_group", ondelete="SET NULL"), nullable=True, index=True)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    warning_km = Column(Numeric(10, 1), nullable=True)
    warning_hours = Column(Numeric(10, 1), nullable=True)
    warning_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1", index=True)

    equipment_model = relationship("EquipmentModel")
    group = relationship("MaintenanceOperationGroup", back_populates="model_operations")
    plan_operations = relationship("MaintenancePlanOperation", back_populates="model_operation")
    records = relationship("MaintenanceRecord", back_populates="model_operation")


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
    is_approved = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
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
        UniqueConstraint("plan_id", "model_operation_id", name="uq_maintenance_plan_model_operation"),
        CheckConstraint(
            "(operation_id IS NOT NULL AND model_operation_id IS NULL) OR "
            "(operation_id IS NULL AND model_operation_id IS NOT NULL)",
            name="ck_maintenance_plan_operation_one_source",
        ),
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
        nullable=True,
        index=True,
    )
    model_operation_id = Column(
        Integer,
        ForeignKey("maintenance_model_operations.id", name="fk_maintenance_plan_operations_model_operation", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    plan = relationship("MaintenancePlan", back_populates="plan_operations")
    operation = relationship("MaintenanceOperation", back_populates="plan_operations")
    model_operation = relationship("MaintenanceModelOperation", back_populates="plan_operations")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        Index("uq_maintenance_record_equipment_operation_date", "equipment_id", "operation_id", "maintenance_date", unique=True),
        Index("uq_maintenance_record_equipment_model_operation_date", "equipment_id", "model_operation_id", "maintenance_date", unique=True),
        CheckConstraint(
            "operation_id IS NULL OR model_operation_id IS NULL",
            name="ck_maintenance_record_one_operation_source",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_id = Column(
        Integer,
        ForeignKey("maintenance_operations.id", name="fk_maintenance_records_operation", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    model_operation_id = Column(
        Integer,
        ForeignKey("maintenance_model_operations.id", name="fk_maintenance_records_model_operation", ondelete="RESTRICT"),
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
    work_order = Column(String(80), nullable=True)
    workshop = Column(String(120), nullable=True)
    # الفني المنفذ: مرجع إلى الفنيين الفعليين في الورشة الداخلية (`workshop_technicians`).
    # عمود اختياري (SET NULL) حتى لا يمنع حذف فنيّ الاحتفاظ بالسجل التاريخي.
    technician_id = Column(
        Integer,
        ForeignKey("workshop_technicians.id", name="fk_maintenance_records_technician_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(30), nullable=False, default="completed")
    is_scheduled = Column(Boolean, nullable=False, default=False, server_default="0")
    # الأعمال المنجزة: وصف العمل الفعلي الذي نُفّذ، منفصل عن الملاحظة.
    description = Column(Text, nullable=True)
    # الملاحظة: ملاحظات إضافية مستقلة عن الأعمال المنجزة.
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    equipment = relationship("Equipment", back_populates="maintenance_records")
    operation = relationship("MaintenanceOperation", back_populates="records", foreign_keys=[operation_id])
    model_operation = relationship("MaintenanceModelOperation", back_populates="records", foreign_keys=[model_operation_id])
    plan = relationship("MaintenancePlan", back_populates="records")
    technician = relationship("Technician", foreign_keys=[technician_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    @property
    def meter_value(self):
        from app.modules.meter_readings.source_values import read_source_value
        return read_source_value(self, "meter_value")

    @meter_value.setter
    def meter_value(self, value):
        from app.modules.meter_readings.source_values import write_source_value
        write_source_value(self, "meter_value", value)


def _validate_record(connection, target, exclude_id=None):
    if target.equipment_id is None:
        raise ValueError("يجب تحديد العتاد قبل تسجيل الصيانة.")
    operation_id = getattr(target, "operation_id", None)
    model_operation_id = getattr(target, "model_operation_id", None)
    if (operation_id is None) == (model_operation_id is None):
        raise ValueError("يجب تحديد عملية الصيانة قبل تسجيل السجل.")
    plan_id = getattr(target, "plan_id", None)
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
            select(MaintenanceOperation.id, MaintenanceOperation.is_active)
            .where(MaintenanceOperation.id == operation_id)
        ).first()
        if operation_row is None:
            raise ValueError("عملية الصيانة المحددة غير موجودة.")
        if not operation_row[1]:
            raise ValueError("عملية الصيانة غير مفعلة.")

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
    else:
        operation_row = connection.execute(
            select(MaintenanceModelOperation.id, MaintenanceModelOperation.is_active, MaintenanceModelOperation.equipment_model_id)
            .where(MaintenanceModelOperation.id == model_operation_id)
        ).first()
        if operation_row is None:
            raise ValueError("عملية الصيانة الخاصة المحددة غير موجودة.")
        if not operation_row[1]:
            raise ValueError("عملية الصيانة الخاصة غير مفعلة.")
        if operation_row[2] != equipment_model_id:
            raise ValueError("عملية الصيانة الخاصة لا تخص طراز العتاد المحدد.")
        membership = connection.execute(
            select(MaintenancePlanOperation.id)
            .join(MaintenancePlan, MaintenancePlan.id == MaintenancePlanOperation.plan_id)
            .where(
                MaintenancePlanOperation.model_operation_id == model_operation_id,
                MaintenancePlan.equipment_model_id == equipment_model_id,
                MaintenancePlan.is_active.is_(True),
            )
        ).first()
        has_any_membership = connection.execute(
            select(MaintenancePlanOperation.id)
            .where(MaintenancePlanOperation.model_operation_id == model_operation_id)
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
        operation_filter = (
            MaintenancePlanOperation.operation_id == operation_id
            if operation_id is not None
            else MaintenancePlanOperation.model_operation_id == model_operation_id
        )
        linked = connection.execute(
            select(MaintenancePlanOperation.id).where(
                MaintenancePlanOperation.plan_id == plan_id,
                operation_filter,
            )
        ).first()
        if linked is None:
            raise ValueError("عملية الصيانة غير مرتبطة بالخطة المحددة.")

    if target.meter_value is None:
        return

    # Chronology is validated and recorded atomically by the central meter
    # ledger listener after this source row is inserted or updated.


def _sync_equipment_current(connection, equipment_id):
    """Keep Equipment.current_* synchronized only with the central meter ledger."""
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
    current_value = connection.execute(
        select(reading_column)
        .where(
            MeterReading.equipment_id == equipment_id,
            reading_column.is_not(None),
            MeterReading.reading_date <= datetime.combine(datetime.now(timezone.utc).date(), datetime.max.time()),
        )
        .order_by(MeterReading.reading_date.desc(), MeterReading.id.desc())
        .limit(1)
    ).scalar_one_or_none()
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
    if any(state.attrs[name].history.has_changes() for name in ("equipment_id", "operation_id", "model_operation_id", "maintenance_date")):
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
