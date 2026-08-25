from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class MaintenanceRule(Base):
    __tablename__ = "maintenance_rules"

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


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("maintenance_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    maintenance_date = Column(Date, nullable=False)
    meter_value = Column(Numeric(10, 1), nullable=True)
    work_order = Column(String(80), nullable=True)
    workshop = Column(String(120), nullable=True)
    status = Column(String(30), nullable=False, default="completed")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    equipment = relationship("Equipment")
    rule = relationship("MaintenanceRule")
