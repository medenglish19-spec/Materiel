from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class SparePartRequest(Base):
    __tablename__ = "spare_part_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_number = Column(String(80), nullable=False, unique=True, index=True)
    request_date = Column(Date, nullable=False, default=date.today, index=True)
    source_type = Column(String(20), nullable=False, index=True)
    fault_id = Column(Integer, ForeignKey("faults.id", ondelete="SET NULL"), nullable=True, index=True)
    repair_id = Column(Integer, ForeignKey("repairs.id", ondelete="SET NULL"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    requested_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("source_type IN ('fault', 'repair')", name="ck_spare_part_request_source_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_spare_part_request_status"),
        CheckConstraint(
            "(source_type = 'fault' AND fault_id IS NOT NULL AND repair_id IS NULL) OR "
            "(source_type = 'repair' AND repair_id IS NOT NULL AND fault_id IS NULL)",
            name="ck_spare_part_request_source_match",
        ),
    )

    items = relationship("SparePartRequestItem", back_populates="request", cascade="all, delete-orphan", order_by="SparePartRequestItem.id")
    fault = relationship("Fault")
    repair = relationship("Repair")
    equipment = relationship("Equipment")
    requested_by = relationship("User")


class SparePartRequestItem(Base):
    __tablename__ = "spare_part_request_items"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("spare_part_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    # الربط بالمخزون اختياري: البند قد يحمل اسماً حراً فقط دون قطعة مرجعية.
    spare_part_id = Column(Integer, ForeignKey("spare_parts.id", ondelete="RESTRICT"), nullable=True, index=True)
    part_name = Column(String(200), nullable=True)
    requested_quantity = Column(Numeric(10, 2), nullable=False)
    received_quantity = Column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    received_date = Column(Date, nullable=True, index=True)
    recipient = Column(String(160), nullable=True)
    supplier_institution = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        # spare_part_id nullable: لا نمنع التكرار على المعرّف الفارغ؛ المنع يتم في الخدمة بالاسم الحر.
        CheckConstraint("requested_quantity > 0", name="ck_spare_part_request_item_requested_positive"),
        CheckConstraint("received_quantity >= 0", name="ck_spare_part_request_item_received_nonnegative"),
    )

    request = relationship("SparePartRequest", back_populates="items")
    spare_part = relationship("SparePart")
