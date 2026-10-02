from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class SparePartRequest(Base):
    __tablename__ = "spare_part_requests"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('maintenance', 'repair', 'tire', 'battery')",
            name="ck_spare_part_request_source_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'partially_fulfilled', 'fulfilled', 'rejected', 'cancelled')",
            name="ck_spare_part_request_status",
        ),
        CheckConstraint(
            "priority IN ('normal', 'urgent')",
            name="ck_spare_part_request_priority",
        ),
        CheckConstraint(
            "(source_type = 'maintenance' AND maintenance_record_id IS NOT NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'repair' AND maintenance_record_id IS NULL AND repair_id IS NOT NULL AND tire_id IS NULL AND battery_id IS NULL) OR "
            "(source_type = 'tire' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NOT NULL AND battery_id IS NULL) OR "
            "(source_type = 'battery' AND maintenance_record_id IS NULL AND repair_id IS NULL AND tire_id IS NULL AND battery_id IS NOT NULL)",
            name="ck_spare_part_request_source_match",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_number = Column(String(50), nullable=False, unique=True, index=True)
    request_date = Column(Date, nullable=False, default=date.today, index=True)
    needed_by_date = Column(Date, nullable=True, index=True)
    source_type = Column(String(20), nullable=False, index=True)
    maintenance_record_id = Column(Integer, ForeignKey("maintenance_records.id", ondelete="SET NULL"), nullable=True, index=True)
    repair_id = Column(Integer, ForeignKey("repairs.id", ondelete="SET NULL"), nullable=True, index=True)
    tire_id = Column(Integer, ForeignKey("tires.id", ondelete="SET NULL"), nullable=True, index=True)
    battery_id = Column(Integer, ForeignKey("batteries.id", ondelete="SET NULL"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    priority = Column(String(20), nullable=False, default="normal", server_default="normal")
    status = Column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    items = relationship("SparePartRequestItem", back_populates="request", cascade="all, delete-orphan", order_by="SparePartRequestItem.id")
    maintenance_record = relationship("MaintenanceRecord")
    repair = relationship("Repair")
    tire = relationship("Tire")
    battery = relationship("Battery")
    equipment = relationship("Equipment")
    requested_by = relationship("User")


class SparePartRequestItem(Base):
    __tablename__ = "spare_part_request_items"
    __table_args__ = (
        UniqueConstraint("request_id", "spare_part_id", name="uq_spare_part_request_item_part"),
        CheckConstraint("requested_quantity > 0", name="ck_spare_part_request_item_requested_positive"),
        CheckConstraint("approved_quantity >= 0", name="ck_spare_part_request_item_approved_nonnegative"),
        CheckConstraint("issued_quantity >= 0", name="ck_spare_part_request_item_issued_nonnegative"),
        CheckConstraint("approved_quantity <= requested_quantity", name="ck_spare_part_request_item_approved_lte_requested"),
        CheckConstraint("issued_quantity <= approved_quantity", name="ck_spare_part_request_item_issued_lte_approved"),
    )

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("spare_part_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_quantity = Column(Numeric(10, 2), nullable=False)
    approved_quantity = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    issued_quantity = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    notes = Column(Text, nullable=True)

    request = relationship("SparePartRequest", back_populates="items")
    spare_part = relationship("SparePart")
