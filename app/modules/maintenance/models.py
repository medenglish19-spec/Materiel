from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Text, Boolean, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship

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
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    equipment_type_id = Column(Integer, ForeignKey("equipment_types.id", ondelete="CASCADE"), nullable=False, index=True)
    interval_km = Column(Numeric(10, 1), nullable=True)
    interval_hours = Column(Numeric(10, 1), nullable=True)
    interval_days = Column(Integer, nullable=True)
    warning_km = Column(Numeric(10, 1), nullable=True, default=1000)
    warning_days = Column(Integer, nullable=True, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)

    equipment_type = relationship("EquipmentType")
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
    meter_value = Column(Numeric(10, 1), nullable=True)
    work_order = Column(String(80), nullable=True)
    workshop = Column(String(120), nullable=True)
    status = Column(String(30), nullable=False, default="completed")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    equipment = relationship("Equipment")
    rule = relationship("MaintenanceRule", back_populates="records")
