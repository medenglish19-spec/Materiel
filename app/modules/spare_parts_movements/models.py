from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class SparePartMovementDocument(Base):
    __tablename__ = "spare_part_movement_documents"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(80), nullable=False, unique=True, index=True)
    document_type = Column(String(20), nullable=False, index=True)
    document_date = Column(Date, nullable=False, default=date.today, index=True)
    issuer = Column(String(160), nullable=False)
    recipient = Column(String(160), nullable=False)
    beneficiary = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    source_document_id = Column(Integer, ForeignKey("spare_part_movement_documents.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("document_type IN ('distribution', 'return')", name="ck_spare_part_movement_document_type"),
    )

    items = relationship("SparePartMovementItem", back_populates="document", cascade="all, delete-orphan", order_by="SparePartMovementItem.id")
    source_document = relationship("SparePartMovementDocument", remote_side=[id], back_populates="return_documents")
    return_documents = relationship("SparePartMovementDocument", back_populates="source_document", cascade="save-update, merge")
    created_by = relationship("User")


class SparePartMovementItem(Base):
    __tablename__ = "spare_part_movement_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("spare_part_movement_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    request_item_id = Column(Integer, ForeignKey("spare_part_request_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_item_id = Column(Integer, ForeignKey("spare_part_movement_items.id", ondelete="RESTRICT"), nullable=True, index=True)
    quantity = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_spare_part_movement_item_quantity_positive"),
        UniqueConstraint("document_id", "request_item_id", name="uq_spare_part_movement_document_item"),
        UniqueConstraint("document_id", "source_item_id", name="uq_spare_part_movement_document_source_item"),
    )

    document = relationship("SparePartMovementDocument", back_populates="items")
    request_item = relationship("SparePartRequestItem")
    source_item = relationship("SparePartMovementItem", remote_side=[id], back_populates="return_items")
    return_items = relationship("SparePartMovementItem", back_populates="source_item", cascade="save-update, merge")
