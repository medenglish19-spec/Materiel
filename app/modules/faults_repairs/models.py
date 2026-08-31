"""Faults, repairs, and spare-parts domain models.

This module is intentionally separate from periodic maintenance rules/records.
A fault belongs to one physical Equipment item; a repair belongs to a fault;
consumed spare parts belong to a repair.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class Fault(Base):
    __tablename__ = "faults"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_fault_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'diagnosing', 'repairing', 'waiting_parts', 'repaired', 'closed')",
            name="ck_fault_status",
        ),
        CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="ck_fault_meter_nonnegative",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(
        Integer, ForeignKey("equipment.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    maintenance_record_id = Column(
        Integer, ForeignKey("maintenance_records.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    reported_date = Column(Date, nullable=False)
    report_number = Column(String(80), nullable=True, index=True)
    note = Column(Text, nullable=True)
    meter_value = Column(Numeric(10, 1), nullable=True)
    fault_type = Column(String(80), nullable=True)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="medium", server_default="medium")
    status = Column(String(30), nullable=False, default="open", server_default="open")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    equipment = relationship("Equipment", back_populates="faults")
    maintenance_record = relationship("MaintenanceRecord")
    created_by = relationship("User", foreign_keys=[created_by_id])
    repairs = relationship(
        "Repair",
        back_populates="fault",
        cascade="all, delete-orphan",
        order_by="Repair.repair_date.desc(), Repair.id.desc()",
    )


class Repair(Base):
    __tablename__ = "repairs"
    __table_args__ = (
        CheckConstraint(
            "workshop_type IN ('internal', 'external')",
            name="ck_repair_workshop_type",
        ),
        CheckConstraint(
            "(workshop_type = 'internal') OR external_dispatch_document IS NOT NULL",
            name="ck_external_repair_requires_dispatch_document",
        ),
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name="ck_repair_status",
        ),
        CheckConstraint(
            "labor_hours IS NULL OR labor_hours >= 0",
            name="ck_repair_labor_hours_nonnegative",
        ),
        CheckConstraint(
            "meter_value IS NULL OR meter_value >= 0",
            name="ck_repair_meter_nonnegative",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    fault_id = Column(
        Integer, ForeignKey("faults.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    repair_date = Column(Date, nullable=False)
    meter_value = Column(Numeric(10, 1), nullable=True)
    diagnosis = Column(Text, nullable=True)
    action_taken = Column(Text, nullable=False)
    technician = Column(String(120), nullable=True)
    workshop_type = Column(String(20), nullable=False, default="internal", server_default="internal")
    workshop = Column(String(120), nullable=True)
    repair_document = Column(String(255), nullable=True)
    external_dispatch_document = Column(String(255), nullable=True)
    labor_hours = Column(Numeric(8, 1), nullable=True)
    status = Column(String(20), nullable=False, default="completed", server_default="completed")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    fault = relationship("Fault", back_populates="repairs")
    consumed_parts = relationship(
        "RepairPart",
        back_populates="repair",
        cascade="all, delete-orphan",
        order_by="RepairPart.id",
    )
    created_by = relationship("User", foreign_keys=[created_by_id])


class SparePart(Base):
    __tablename__ = "spare_parts"
    __table_args__ = (
        UniqueConstraint("part_number", name="uq_spare_part_number"),
        CheckConstraint(
            "is_active IN (0, 1)",
            name="ck_spare_part_active",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    part_number = Column(String(80), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    receiving_document = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)


class RepairPart(Base):
    __tablename__ = "repair_parts"
    __table_args__ = (
        UniqueConstraint("repair_id", "spare_part_id", name="uq_repair_spare_part"),
        CheckConstraint("quantity > 0", name="ck_repair_part_quantity_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    repair_id = Column(
        Integer, ForeignKey("repairs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    spare_part_id = Column(
        Integer, ForeignKey("spare_parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    quantity = Column(Numeric(10, 2), nullable=False)
    distribution_document = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)

    repair = relationship("Repair", back_populates="consumed_parts")
    spare_part = relationship("SparePart")
